"""LAN host/guest page with lobby seats and 2-/4-player boards."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.engine import BestMove, EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.app.match import match_kind_from_mode, match_kind_key
from chess_core.app.network_game import (
    GuestTurnTransport,
    HostTurnTransport,
    NetworkedLocalGameService,
)
from chess_core.app.seats import (
    BOARD_A,
    BOARD_B,
    BOARD_MAIN,
    SPECTATOR,
    SeatDuty,
    partner_board,
    spec_by_id,
)
from chess_core.core.notation import with_partner_engine_fen
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.lan import lan_ipv4_addresses
from chess_core.infra.network import GameServer
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    HelloOkPayload,
    LobbyState,
    MatchEnvelope,
    StateEnvelope,
    UndoPending,
)
from chess_core.infra.tcp_client import HelloRejectedError, TcpGameClient
from chess_core.infra.tcp_server import TcpGameServer
from chess_core.ui.piece_keys import drop_flip_map, droppable_type_names, piece_asset_key
from chess_core.ui.engine_bridge import EngineBridge
from chess_core.ui.theme import mode_display_name, tighten_wrapping_label
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.match_lobby import MatchLobbyWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketWidget
from chess_core.ui.widgets.promotion_menu import choose_promotion_move


class _AsyncLoopThread(QThread):
    def __init__(self) -> None:
        super().__init__()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._ready = asyncio.Event() if False else None

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        loop.call_soon(self._mark_ready)
        loop.run_forever()
        loop.close()

    def _mark_ready(self) -> None:
        self._started = True

    def wait_ready(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while self.loop is None:
            if time.monotonic() > deadline:
                raise RuntimeError("network event loop failed to start")
            time.sleep(0.01)

    def stop(self) -> None:
        loop = self.loop
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        self.wait(2000)


class NetworkSignals(QObject):
    message = pyqtSignal(object)
    error = pyqtSignal(str)
    peer_ready = pyqtSignal()


class NetworkGameWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
        discovered: list | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._discovered = discovered
        self._mode_id = mode_id
        self._loop_thread: _AsyncLoopThread | None = None
        self._tcp_server: TcpGameServer | None = None
        self._tcp_client: TcpGameClient | None = None
        self._game_server: GameServer | None = None
        self._host_session_id: str | None = None
        self._own_session_id = ""
        self._is_host = False
        self._match_kind = "single"
        self._transport: HostTurnTransport | GuestTurnTransport | None = None
        self._services: dict[str, NetworkedLocalGameService] = {}
        self._selected: dict[str, int | None] = {}
        self._drop_type: str | None = None
        self._drop_face: str | None = None
        self._seat = SPECTATOR
        self._seats: set[str] = set()
        self._bot_sessions: dict[str, str] = {}
        self._bot_bridges: dict[str, EngineBridge] = {}
        self._bot_busy: set[str] = set()
        self._clocks: dict = {}
        self._analysis_board = BOARD_MAIN
        self._signals = NetworkSignals(self)
        self._signals.message.connect(self._on_network_message)
        self._signals.error.connect(self._on_network_error)
        self._signals.peer_ready.connect(self._on_peer_ready)

        self.host_button = QPushButton("Создать стол")
        self.join_button = QPushButton("Подключиться")
        self.host_input = QLineEdit("127.0.0.1")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(DEFAULT_GAME_PORT)
        self.status = QLabel(_lan_text())
        tighten_wrapping_label(self.status)
        self.lobby = MatchLobbyWidget()
        self.lobby.seat_chosen.connect(self._on_seat_chosen)
        self.lobby.start_requested.connect(self._on_start_match)
        self.fill_bots = QCheckBox("Заполнить свободные места движком")
        self.fill_bots.setToolTip(
            "При старте свободные места займёт Fairy-Stockfish (или встроенный "
            "движок, если Fairy не найден). Каждый ход движок видит свою доску, "
            "карман с подарками партнёра и FEN второй доски."
        )
        self.two_engine_processes = QCheckBox("Два процесса движка")
        self.two_engine_processes.setChecked(True)
        self.two_engine_processes.setToolTip(
            "Включено: отдельный процесс на каждую доску. "
            "Выключено: один процесс последовательно играет на обеих досках."
        )

        self.board_a = BoardWidget()
        self.board_b = BoardWidget()
        self.board_a.set_piece_drag_enabled(True)
        self.board_b.set_piece_drag_enabled(True)
        self.pocket_a = PocketWidget()
        self.pocket_b = PocketWidget()
        self.clock_a = GameClockWidget()
        self.clock_b = GameClockWidget()
        self.board_b_panel = QWidget()
        self._hnb_hint = QLabel("")
        tighten_wrapping_label(self._hnb_hint)

        connect_row = QHBoxLayout()
        connect_row.addWidget(self.host_button)
        connect_row.addWidget(QLabel("IP"))
        connect_row.addWidget(self.host_input)
        connect_row.addWidget(QLabel("Порт"))
        connect_row.addWidget(self.port_input)
        connect_row.addWidget(self.join_button)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.board_a)
        left_layout.addWidget(self.pocket_a)
        left_layout.addWidget(self.clock_a)
        right_layout = QVBoxLayout(self.board_b_panel)
        right_layout.addWidget(self.board_b)
        right_layout.addWidget(self.pocket_b)
        right_layout.addWidget(self.clock_b)

        boards = QSplitter()
        boards.addWidget(left)
        boards.addWidget(self.board_b_panel)

        self.move_list = MoveListWidget()
        self.live_button = QPushButton("К партии")
        self.live_button.setEnabled(False)
        analysis = QWidget()
        analysis_layout = QVBoxLayout(analysis)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_title = QLabel("Ходы")
        analysis_title.setObjectName("panelTitle")
        analysis_layout.addWidget(analysis_title)
        analysis_layout.addWidget(self.move_list, 1)
        analysis_layout.addWidget(self.live_button)

        play_row = QSplitter()
        play_row.addWidget(boards)
        play_row.addWidget(analysis)
        play_row.setStretchFactor(0, 4)
        play_row.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addLayout(connect_row)
        layout.addWidget(self.status)
        layout.addWidget(self.lobby)
        layout.addWidget(self.fill_bots)
        layout.addWidget(self.two_engine_processes)
        layout.addWidget(self._hnb_hint)
        layout.addWidget(play_row, 1)

        self.host_button.clicked.connect(self._host_game)
        self.join_button.clicked.connect(self._join_game)
        self.live_button.clicked.connect(self._go_live)
        self.move_list.revision_selected.connect(self._on_revision_selected)
        self.board_a.square_clicked.connect(lambda index: self._on_square(BOARD_A if self._match_kind == "bughouse" else BOARD_MAIN, index))
        self.board_b.square_clicked.connect(lambda index: self._on_square(BOARD_B, index))
        self.pocket_a.piece_chosen.connect(lambda name: self._on_drop_type(name))
        self.pocket_b.piece_chosen.connect(lambda name: self._on_drop_type(name))
        self.fill_bots.toggled.connect(self.lobby.set_allow_incomplete_start)
        self.set_mode(mode_id)

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        mode = self._resolve(mode_id)
        self._match_kind = match_kind_key(match_kind_from_mode(mode))
        self.board_b_panel.setVisible(self._match_kind == "bughouse")
        self.fill_bots.setVisible(self._match_kind == "bughouse")
        self.two_engine_processes.setVisible(self._match_kind == "bughouse")
        self.pocket_a.setVisible(self._match_kind in {"bughouse", "single"} and mode.drop_rule is not None)
        self.pocket_b.setVisible(self._match_kind == "bughouse")

    def disconnect(self) -> None:
        client = self._tcp_client
        server = self._tcp_server
        thread = self._loop_thread
        if thread is not None and thread.loop is not None:
            if client is not None:
                asyncio.run_coroutine_threadsafe(client.close(), thread.loop)
            if server is not None:
                asyncio.run_coroutine_threadsafe(server.close(), thread.loop)
            thread.stop()
        self._tcp_client = None
        self._tcp_server = None
        self._game_server = None
        self._loop_thread = None
        self._transport = None
        self._services.clear()
        self._shutdown_bot_engines()
        self._bot_sessions.clear()
        self._seats.clear()

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self.disconnect()
        super().closeEvent(event)

    def host_from_position(self, state: GameState) -> None:
        """Host a new table from an editor position. Replaces an existing table."""

        self._host_game(initial_state=state)
        self.status.setText(
            f"{self.status.text()} Стартовая позиция из редактора."
        )

    def _host_game(self, initial_state: GameState | None = None) -> None:
        self.disconnect()
        mode = self._resolve(self._mode_id)
        server = GameServer(
            initial_state if initial_state is not None else mode.initial_state(),
            mode=mode,
            time_control=TimeControlConfig.blitz(),
        )
        host_session = server.connect_client()
        loop_thread = self._start_loop()
        assert loop_thread.loop is not None

        def _flush() -> None:
            tcp = self._tcp_server
            if tcp is not None and loop_thread.loop is not None:
                asyncio.run_coroutine_threadsafe(tcp.flush(), loop_thread.loop)
            session = server._sessions.get(host_session.session_id)
            if session is None:
                return
            pending = list(session.inbox)
            session.inbox.clear()
            for message in pending:
                self._signals.message.emit(message)

        tcp = TcpGameServer(
            server,
            port=int(self.port_input.value()),
            on_remote_event=lambda _session: self._signals.peer_ready.emit(),
            on_game_message=lambda _sid, message: self._signals.message.emit(message),
        )
        self._tcp_server = tcp
        self._game_server = server
        self._host_session_id = host_session.session_id
        self._own_session_id = host_session.session_id
        self._is_host = True
        self._transport = HostTurnTransport(server, host_session.session_id, on_flush=_flush)
        start = initial_state if initial_state is not None else mode.initial_state()
        self._attach_services(mode, match_ready=self._match_kind == "single", initial_state=start)
        self.lobby.set_context(
            match_kind=self._match_kind,
            session_id=host_session.session_id,
            is_host=True,
        )
        asyncio.run_coroutine_threadsafe(tcp.start(), loop_thread.loop)
        self._lock_connection_controls()
        addresses = ", ".join(lan_ipv4_addresses())
        self.status.setText(
            f"Стол {mode_display_name(self._mode_id)} на {addresses}:{self.port_input.value()}. "
            "Гости подключаются по IP."
        )
        self._refresh()

    def _join_game(self) -> None:
        self.disconnect()
        loop_thread = self._start_loop()
        assert loop_thread.loop is not None
        client = TcpGameClient(
            on_message=lambda message: self._signals.message.emit(message),
            mode_resolver=self._resolve,
        )
        self._tcp_client = client

        async def _connect() -> None:
            try:
                hello = await client.connect(
                    self.host_input.text().strip() or "127.0.0.1",
                    int(self.port_input.value()),
                    mode=self._resolve(self._mode_id),
                )
            except HelloRejectedError as exc:
                self._signals.error.emit(_reject_text(exc.reason))
                return
            except OSError as exc:
                self._signals.error.emit(str(exc))
                return
            self._signals.message.emit(hello)

        asyncio.run_coroutine_threadsafe(_connect(), loop_thread.loop)
        self._lock_connection_controls()

    def _attach_guest(self, hello: HelloOkPayload) -> None:
        mode = self._resolve(hello.mode_id)
        self._mode_id = hello.mode_id
        self._match_kind = hello.match_kind
        self._own_session_id = hello.session_id
        self._is_host = hello.is_host
        self._seat = hello.seat
        assert self._tcp_client is not None and self._loop_thread is not None
        self._transport = GuestTurnTransport(
            self._tcp_client,
            schedule=lambda coro: asyncio.run_coroutine_threadsafe(coro, self._loop_thread.loop),
        )
        self._attach_services(mode, match_ready=False)
        self.lobby.set_context(
            match_kind=self._match_kind,
            session_id=hello.session_id,
            is_host=hello.is_host,
        )
        self.status.setText(f"Подключено к {mode_display_name(hello.mode_id)}.")
        self.set_mode(hello.mode_id)

    def _attach_services(
        self,
        mode: GameMode,
        *,
        match_ready: bool,
        initial_state: GameState | None = None,
    ) -> None:
        assert self._transport is not None
        boards = (BOARD_A, BOARD_B) if self._match_kind == "bughouse" else (BOARD_MAIN,)
        self._services = {
            board_id: NetworkedLocalGameService(
                mode,
                self._transport,
                initial_state,
                match_ready=match_ready,
                board_id=board_id,
            )
            for board_id in boards
        }
        self._selected = {board_id: None for board_id in boards}
        self._analysis_board = boards[0]

    def _on_network_message(self, message: object) -> None:
        if isinstance(message, HelloOkPayload) and not self._is_host:
            self._attach_guest(message)
        if isinstance(message, LobbyState):
            self.lobby.apply_lobby(message)
            self._seats = {
                occupant.seat
                for occupant in message.occupants
                if occupant.session_id == self._own_session_id
                and occupant.seat != SPECTATOR
            }
            self._seat = next(iter(self._seats), SPECTATOR)
        for service in self._services.values():
            service.apply_server_message(message)
        if isinstance(message, MatchEnvelope):
            self._clocks = dict(message.clocks)
        elif isinstance(message, StateEnvelope) and message.clock is not None:
            self._clocks["main"] = message.clock
        if isinstance(message, (MatchEnvelope, StateEnvelope, LobbyState, UndoPending, HelloOkPayload)):
            self._refresh()
        if isinstance(message, MatchEnvelope):
            QTimer.singleShot(0, self._schedule_bughouse_bots)
        if self._game_server is not None:
            self.lobby.apply_lobby(self._game_server.lobby_state())
            self._refresh()

    def _on_seat_chosen(self, seat: str) -> None:
        if self._transport is None:
            return
        self._transport.claim_seat(seat)

    def _on_start_match(self) -> None:
        if self._transport is None:
            return
        try:
            if (
                self._match_kind == "bughouse"
                and self.fill_bots.isChecked()
                and self._game_server is not None
            ):
                self._bot_sessions.update(
                    self._game_server.fill_empty_seats_with_bots()
                )
                self._ensure_bughouse_engines()
            self._transport.start_match()
            self.fill_bots.setEnabled(False)
            self.two_engine_processes.setEnabled(False)
        except PermissionError as exc:
            self.status.setText(str(exc))
            return
        QTimer.singleShot(0, self._schedule_bughouse_bots)

    def _on_drop_type(self, name: str) -> None:
        self._drop_type = name
        sender = self.sender()
        self._drop_face = sender.selected_face() if isinstance(sender, PocketWidget) else name

    def _on_square(self, board_id: str, index: int) -> None:
        self._analysis_board = board_id
        service = self._services.get(board_id)
        if service is None or not service.match_ready:
            return
        if not service.is_live:
            self.status.setText("Просмотр партии. «К партии» — вернуться к текущей позиции.")
            self._refresh()
            return
        spec = self._own_spec_for_board(board_id, service.state.side_to_move)
        if spec is None:
            return
        if spec.duty is SeatDuty.BRAIN:
            piece = service.state.board_state.piece_at(index)
            if piece is None or piece.side is not spec.side:
                return
            assert self._transport is not None
            try:
                self._transport.brain_select(piece.piece_type.name, board_id)
            except (PermissionError, ValueError) as exc:
                self.status.setText(str(exc))
            return
        if spec.duty is SeatDuty.HAND and service.chosen_piece_type is None:
            self.status.setText("Ждём, пока Brain выберет тип фигуры.")
            return
        if spec.side is not service.state.side_to_move:
            return
        if self._drop_type is not None:
            shape = service.mode.board.shape
            target = Square.from_index(index, shape.files, shape.ranks)
            drop = DropAction(PieceTypeId(self._drop_type), target, self._drop_face)
            try:
                service.play_turn(Turn(spec.side, [drop]))
            except (PermissionError, ValueError):
                pass
            self._drop_type = None
            self._drop_face = None
            self.pocket_a.clear_selection()
            self.pocket_b.clear_selection()
            self._refresh()
            return
        piece = service.state.board_state.piece_at(index)
        selected = self._selected.get(board_id)
        if selected is None:
            if piece is not None and piece.side is spec.side:
                if spec.duty is SeatDuty.HAND and piece.piece_type.name != service.chosen_piece_type:
                    return
                self._selected[board_id] = index
                service.legal_moves_for_square(index)
                self._refresh()
            return
        if piece is not None and piece.side is spec.side:
            self._selected[board_id] = index
            service.legal_moves_for_square(index)
            self._refresh()
            return
        shape = service.mode.board.shape
        source = Square.from_index(selected, shape.files, shape.ranks)
        target = Square.from_index(index, shape.files, shape.ranks)
        candidates = [
            move
            for move in service.selected_moves
            if move.from_square == source and move.to_square == target
        ]
        if not candidates:
            self._selected[board_id] = None
            self._refresh()
            return
        source_piece = service.state.board_state.piece_at(selected)
        move = self._choose_promotion(
            candidates,
            side=spec.side,
            asset_family=service.mode.asset_family,
            unpromoted_type=None if source_piece is None else source_piece.piece_type.name,
        )
        if move is None:
            return
        try:
            service.play_turn(Turn(spec.side, [move]))
        except (PermissionError, ValueError) as exc:
            self.status.setText(str(exc))
        self._selected[board_id] = None
        self._refresh()

    def _choose_promotion(
        self,
        candidates: list[MoveAction],
        *,
        side: PieceSide,
        asset_family: str,
        unpromoted_type: str | None,
    ) -> MoveAction | None:
        return choose_promotion_move(
            candidates,
            parent=self,
            side=side,
            asset_family=asset_family,
            unpromoted_type=unpromoted_type,
        )

    def _own_spec_for_board(
        self, board_id: str, side: PieceSide | None = None
    ):
        seats = self._seats or ({self._seat} if self._seat != SPECTATOR else set())
        for seat in seats:
            spec = spec_by_id(self._match_kind, seat)
            if spec is None or spec.board_id != board_id:
                continue
            if side is None or spec.side is side:
                return spec
        return None

    def _refresh(self) -> None:
        primary_spec = spec_by_id(self._match_kind, self._seat)
        mapping = {
            BOARD_MAIN: (self.board_a, self.pocket_a, self.clock_a),
            BOARD_A: (self.board_a, self.pocket_a, self.clock_a),
            BOARD_B: (self.board_b, self.pocket_b, self.clock_b),
        }
        for board_id, service in self._services.items():
            board, pocket, clock = mapping[board_id]
            _paint_board(board, service)
            spec = (
                self._own_spec_for_board(board_id)
                if self._match_kind == "bughouse"
                else primary_spec
            )
            own_board = spec is not None and spec.board_id == board_id
            orientation = BoardOrientation.WHITE
            if spec is not None and own_board and spec.side is PieceSide.BLACK:
                orientation = BoardOrientation.BLACK
            elif spec is not None and not own_board and self._match_kind == "bughouse":
                orientation = (
                    BoardOrientation.BLACK
                    if spec.side is PieceSide.WHITE
                    else BoardOrientation.WHITE
                )
            board.set_orientation(orientation)
            pocket.set_hands(
                service.state.hands,
                spec.side if spec is not None and own_board else PieceSide.WHITE,
                enabled=own_board and spec is not None and spec.duty is SeatDuty.MOVER and service.match_ready,
                types=droppable_type_names(service.mode),
                asset_family=service.mode.asset_family,
                grid=True,
                flip_map=drop_flip_map(service.mode),
                facing_black=orientation is BoardOrientation.BLACK,
            )
            snapshot = self._clocks.get(board_id) or self._clocks.get(BOARD_MAIN)
            if snapshot is None and self._game_server is not None:
                snapshot = self._game_server.match.clock_snapshots().get(board_id)
            clock.set_snapshot(snapshot, client_mono_ms=int(time.monotonic() * 1000))
            selected = self._selected.get(board_id)
            legal = set()
            if selected is not None:
                legal = {
                    move.to_square.index(service.mode.board.shape.files)
                    for move in service.selected_moves
                }
            type_squares: set[int] = set()
            blocked: set[int] = set()
            chosen = service.chosen_piece_type
            if spec is not None and spec.board_id == board_id and chosen:
                for index, piece in service.state.board_state.cells.items():
                    if piece is None or piece.side is not spec.side:
                        continue
                    if piece.piece_type.name == chosen:
                        type_squares.add(index)
                    else:
                        blocked.add(index)
            board.set_highlights(
                selected=selected,
                legal_destinations=legal,
                type_highlights=type_squares,
                blocked_squares=blocked,
            )
        if self._match_kind == "hand_and_brain":
            spec = primary_spec
            if spec is None:
                self._hnb_hint.setText("Вы зритель.")
            elif spec.duty is SeatDuty.BRAIN:
                self._hnb_hint.setText("Brain: кликните свою фигуру. Hand увидит только тип.")
            else:
                chosen = next(iter(self._services.values())).chosen_piece_type if self._services else None
                self._hnb_hint.setText(
                    "Hand: ждите тип от Brain." if not chosen else f"Hand: ходите фигурой {chosen}."
                )
        else:
            self._hnb_hint.setText("")
        if self._game_server is not None:
            lobby = self._game_server.lobby_state()
            self._seats = {
                occupant.seat
                for occupant in lobby.occupants
                if occupant.session_id == self._own_session_id
                and occupant.seat != SPECTATOR
            }
            self._seat = next(iter(self._seats), SPECTATOR)
        self._refresh_move_list()

    def _active_service(self) -> NetworkedLocalGameService | None:
        if self._analysis_board in self._services:
            return self._services[self._analysis_board]
        if BOARD_MAIN in self._services:
            return self._services[BOARD_MAIN]
        return next(iter(self._services.values()), None)

    def _refresh_move_list(self) -> None:
        service = self._active_service()
        if service is None:
            self.move_list.set_moves((), live_revision=0, view_revision=0)
            self.live_button.setEnabled(False)
            return
        self.move_list.set_moves(
            service.move_log_lines,
            live_revision=service.record.live_revision,
            view_revision=service.record.view_revision,
        )
        self.live_button.setEnabled(not service.is_live)

    def _on_revision_selected(self, revision: int) -> None:
        service = self._active_service()
        if service is None:
            return
        service.go_to_revision(revision)
        self._selected[service.board_id] = None
        self._refresh()

    def _go_live(self) -> None:
        service = self._active_service()
        if service is None:
            return
        service.go_live()
        self._refresh()

    def _ensure_bughouse_engines(self) -> None:
        if not self._bot_sessions or self._bot_bridges:
            return
        mode = self._resolve(self._mode_id)
        keys = (
            (BOARD_A, BOARD_B)
            if self.two_engine_processes.isChecked()
            else ("shared",)
        )
        for key in keys:
            service = EngineAnalysisService.for_mode(mode, self._discovered)
            bridge = EngineBridge(service, self)
            bridge.analysis_ready.connect(self._on_bughouse_bot_analysis)
            self._bot_bridges[key] = bridge

    def _schedule_bughouse_bots(self) -> None:
        server = self._game_server
        if (
            server is None
            or self._match_kind != "bughouse"
            or server.match.state.phase.name != "PLAYING"
            or not self._bot_sessions
        ):
            return
        self._ensure_bughouse_engines()
        shared = "shared" in self._bot_bridges
        if shared and self._bot_busy:
            return
        for board_id in (BOARD_A, BOARD_B):
            state = server.match.board(board_id)
            side = "white" if state.side_to_move is PieceSide.WHITE else "black"
            seat = f"{board_id.lower()}_{side}"
            session_id = self._bot_sessions.get(seat)
            if session_id is None:
                continue
            key = "shared" if shared else board_id
            if key in self._bot_busy:
                continue
            bridge = self._bot_bridges.get(key)
            if bridge is None:
                continue
            self._bot_busy.add(key)
            partner = server.match.board(partner_board(board_id))
            bridge.request_analysis(
                EngineRequest(
                    with_partner_engine_fen(state, partner),
                    SearchLimit(movetime_ms=400),
                    purpose=f"bughouse|{key}|{board_id}|{session_id}",
                    revision=server.revision,
                )
            )
            if shared:
                break

    def _on_bughouse_bot_analysis(self, result: BestMove) -> None:
        parts = result.purpose.split("|")
        if len(parts) != 4 or parts[0] != "bughouse":
            return
        _, key, board_id, session_id = parts
        self._bot_busy.discard(key)
        server = self._game_server
        if (
            server is None
            or result.revision != server.revision
            or result.turn is None
            or server.match.state.phase.name != "PLAYING"
        ):
            QTimer.singleShot(0, self._schedule_bughouse_bots)
            return
        try:
            server.apply_remote_turn(session_id, result.turn, board_id=board_id)
        except (PermissionError, ValueError) as exc:
            self.status.setText(f"Ход движка отклонён: {exc}")
        self._drain_host_inbox()
        tcp = self._tcp_server
        thread = self._loop_thread
        if tcp is not None and thread is not None and thread.loop is not None:
            asyncio.run_coroutine_threadsafe(tcp.flush(), thread.loop)
        self._refresh()
        QTimer.singleShot(25, self._schedule_bughouse_bots)

    def _shutdown_bot_engines(self) -> None:
        for bridge in set(self._bot_bridges.values()):
            try:
                bridge.analysis_ready.disconnect(self._on_bughouse_bot_analysis)
            except TypeError:
                pass
            bridge.shutdown()
            bridge.deleteLater()
        self._bot_bridges.clear()
        self._bot_busy.clear()

    def _on_peer_ready(self) -> None:
        self._drain_host_inbox()
        self._refresh()

    def _drain_host_inbox(self) -> None:
        server = self._game_server
        session_id = self._host_session_id
        if server is None or session_id is None:
            return
        session = server._sessions.get(session_id)
        if session is None:
            return
        pending = list(session.inbox)
        session.inbox.clear()
        for message in pending:
            self._on_network_message(message)

    def _on_network_error(self, text: str) -> None:
        self.status.setText(text)
        QMessageBox.warning(self, "Сеть", text)

    def _start_loop(self) -> _AsyncLoopThread:
        thread = _AsyncLoopThread()
        thread.start()
        thread.wait_ready()
        self._loop_thread = thread
        return thread

    def _lock_connection_controls(self) -> None:
        self.host_button.setEnabled(False)
        self.join_button.setEnabled(False)
        self.port_input.setEnabled(False)
        self.host_input.setEnabled(False)


def _paint_board(board: BoardWidget, service: NetworkedLocalGameService) -> None:
    position: dict[int, str] = {}
    shape = service.mode.board.shape
    board.set_shape(shape.files, shape.ranks)
    for index, piece in service.state.board_state.cells.items():
        if piece is None:
            continue
        key = piece_asset_key(piece, service.mode.asset_family)
        if key is not None:
            position[index] = key
    board.set_position(position)


def _lan_text() -> str:
    addresses = ", ".join(lan_ipv4_addresses())
    return f"Локальные адреса: {addresses}. Хост создаёт стол, гости вводят IP."


def _reject_text(reason: str) -> str:
    mapping = {
        "protocol_mismatch": "Разные версии протокола.",
        "version_mismatch": "Разные версии программы.",
        "game_full": "За столом больше нет мест.",
        "bad_hello": "Некорректное приветствие.",
    }
    return mapping.get(reason, reason)
