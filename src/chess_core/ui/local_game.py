"""Thin PyQt adapter for a local game service."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.clock import GameClockService
from chess_core.app.game import GameStatus, LocalGameService
from chess_core.app.sound import SoundEvent
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction
from chess_core.core.piece import PieceSide
from chess_core.core.rules import VictoryKind
from chess_core.core.state import GameState, HandsState
from chess_core.core.time_control import TimeControlConfig, TimeControlKind
from chess_core.infra.pgn_storage import PgnMetadata, PgnStorage
from chess_core.ui.piece_assets import (
    FACING_ASSET_FAMILIES,
    hand_slot_types,
    piece_svg_key,
    piece_svg_key_for,
    shogi_hand_order,
)
from chess_core.ui.pgn_save_dialog import PgnSaveDialog
from chess_core.ui.theme import mode_display_name
from chess_core.ui.sound_player import SoundPlayer
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import PlayerClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketStack, PocketWidget

_POCKET_ORDER = ("pawn", "knight", "bishop", "rook", "queen", "king")

_TERMINAL_STATUSES = frozenset(
    (GameStatus.CHECKMATE, GameStatus.STALEMATE, GameStatus.VARIANT_WIN)
)


class _MonoClock:
    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)


class LocalGameWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
        *,
        allow_temporary_variations: bool = False,
        timeline_per_ply: bool = False,
        include_initial_position: bool = False,
        show_clock: bool = True,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._allow_temporary_variations = allow_temporary_variations
        self._timeline_per_ply = timeline_per_ply
        self._include_initial_position = include_initial_position
        self._show_clock = show_clock
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._service: LocalGameService | None = None
        self._selected: int | None = None
        self._clock_service: GameClockService | None = None
        self._pgn_offered_revision: int | None = None
        self.board = BoardWidget()
        self.status = QLabel()
        self.status.setObjectName("gameStatus")
        self.move_list = MoveListWidget()
        self.black_clock = PlayerClockWidget(PieceSide.BLACK)
        self.white_clock = PlayerClockWidget(PieceSide.WHITE)
        self.clock_mode = QLabel("")
        self.clock_mode.setObjectName("panelTitle")
        self.clock_mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not self._show_clock:
            self.black_clock.hide()
            self.white_clock.hide()
            self.clock_mode.hide()
        self.evaluation_bar = EvaluationBarWidget()
        self.black_pocket = PocketWidget(PieceSide.BLACK)
        self.white_pocket = PocketWidget(PieceSide.WHITE)
        self.black_pocket.hide()
        self.white_pocket.hide()
        self._sounds = SoundPlayer()
        self.instructions = QLabel(
            "Ход: щёлкните фигуру и клетку. В crazyhouse фигура из кармана, "
            "затем пустая клетка. В duck chess после хода поставьте утку. "
            "F — перевернуть; Ctrl+Z — отмена; R — новая игра после окончания."
        )
        self.instructions.setObjectName("gameHint")
        self.instructions.setWordWrap(True)
        self.new_game_button = QPushButton("Новая игра / Сброс")
        self.live_button = QPushButton("К текущей позиции")
        self.mainline_button = QPushButton("Вернуться к основной линии")
        self.mainline_button.hide()
        self.pgn_button = QPushButton("Копировать PGN")
        self.save_pgn_button = QPushButton("Сохранить PGN")
        self.quit_button = QPushButton("Выйти")

        main_split = QSplitter()
        board_panel = QWidget()
        board_layout = QVBoxLayout(board_panel)
        board_layout.addWidget(self.status)

        self._top_bar = QWidget()
        self._top_bar_layout = QHBoxLayout(self._top_bar)
        self._top_bar_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.addWidget(self._top_bar, 0, Qt.AlignmentFlag.AlignHCenter)

        self._clock_rail = QWidget()
        self._clock_rail.setFixedWidth(148)
        self._clock_rail_layout = QVBoxLayout(self._clock_rail)
        self._clock_rail_layout.setContentsMargins(0, 0, 0, 0)
        if not self._show_clock:
            self._clock_rail.hide()

        self._hand_rail = QWidget()
        self._hand_rail_layout = QVBoxLayout(self._hand_rail)
        self._hand_rail_layout.setContentsMargins(0, 0, 0, 0)

        board_row = QWidget()
        board_row_layout = QHBoxLayout(board_row)
        board_row_layout.setContentsMargins(0, 0, 0, 0)
        board_row_layout.addWidget(self._clock_rail, 0, Qt.AlignmentFlag.AlignVCenter)
        board_row_layout.addWidget(self.board, 1)
        board_row_layout.addWidget(self._hand_rail, 0, Qt.AlignmentFlag.AlignVCenter)
        board_layout.addWidget(board_row, 1)

        self._bottom_bar = QWidget()
        self._bottom_bar_layout = QHBoxLayout(self._bottom_bar)
        self._bottom_bar_layout.setContentsMargins(0, 0, 0, 0)
        board_layout.addWidget(self._bottom_bar, 0, Qt.AlignmentFlag.AlignHCenter)

        board_layout.addWidget(self.instructions)
        controls = QHBoxLayout()
        controls.addWidget(self.new_game_button)
        controls.addWidget(self.live_button)
        controls.addWidget(self.mainline_button)
        controls.addWidget(self.pgn_button)
        controls.addWidget(self.save_pgn_button)
        controls.addStretch()
        controls.addWidget(self.quit_button)
        board_layout.addLayout(controls)
        self._board_layout = board_layout

        sidebar = QWidget()
        sidebar.setMinimumWidth(380)
        sidebar_layout = QVBoxLayout(sidebar)
        moves_title = QLabel("Запись партии")
        moves_title.setObjectName("panelTitle")
        sidebar_layout.addWidget(self.clock_mode)
        sidebar_layout.addWidget(self.evaluation_bar)
        sidebar_layout.addWidget(moves_title)
        sidebar_layout.addWidget(self.move_list)

        main_split.addWidget(board_panel)
        main_split.addWidget(sidebar)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 2)
        main_split.setSizes([620, 440])
        self._main_split = main_split
        self._split_initialized = False

        layout = QVBoxLayout(self)
        layout.addWidget(main_split)

        self.board.square_clicked.connect(self._on_square)
        self.white_pocket.piece_clicked.connect(self._on_pocket_piece)
        self.black_pocket.piece_clicked.connect(self._on_pocket_piece)
        self.new_game_button.clicked.connect(self.reset_game)
        self.live_button.clicked.connect(self._go_live)
        self.mainline_button.clicked.connect(self._return_to_mainline)
        self.pgn_button.clicked.connect(self.copy_pgn)
        self.save_pgn_button.clicked.connect(self.save_pgn_dialog)
        self.quit_button.clicked.connect(self._quit)
        self.move_list.revision_selected.connect(self._on_revision_selected)
        self._flip_shortcut = QShortcut(QKeySequence("F"), self)
        self._flip_shortcut.activated.connect(self.flip_board)
        self._shift_flip_shortcut = QShortcut(QKeySequence("Shift+F"), self)
        self._shift_flip_shortcut.activated.connect(self.flip_board)
        self._reset_shortcut = QShortcut(QKeySequence("R"), self)
        self._reset_shortcut.activated.connect(self.reset_finished_game)
        self._undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self.undo_move)
        self._left_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self._left_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._left_shortcut.activated.connect(lambda: self._navigate_revision(-1))
        self._right_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self._right_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._right_shortcut.activated.connect(lambda: self._navigate_revision(1))

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._tick_clock_display)
        if self._show_clock:
            self._ui_timer.start()

        self.set_mode(mode_id)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        if not self._split_initialized:
            self._main_split.setSizes([620, 440])
            self._split_initialized = True

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        mode = self._resolve(mode_id)
        self._service = LocalGameService(
            mode,
            allow_temporary_variations=self._allow_temporary_variations,
        )
        self._clock_service = (
            GameClockService(
                TimeControlConfig.blitz(),
                _MonoClock(),
                starting_side=mode.starting_side,
            )
            if self._show_clock
            else None
        )
        self._pgn_offered_revision = None
        self._selected = None
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
        self.board.set_facing_opponent(mode.facing_opponent)
        self.board.set_orientation(
            BoardOrientation.BLACK
            if mode.default_view_side is PieceSide.BLACK
            else BoardOrientation.WHITE
        )
        self._sync_seat_layout()
        self._sounds.play(SoundEvent.GAME_START)
        self._refresh()

    def load_position(self, state: GameState) -> None:
        self.service.load_position(state)
        self._selected = None
        self._refresh()

    def load_pgn(self, text: str) -> None:
        self.service.import_pgn(text)
        self._selected = None
        self._refresh()

    @property
    def service(self) -> LocalGameService:
        if self._service is None:
            raise RuntimeError("No game mode is loaded")
        return self._service

    def reset_game(self) -> None:
        self.service.reset()
        if self._clock_service is not None:
            self._clock_service = GameClockService(
                self._clock_service._config,
                _MonoClock(),
                starting_side=self.service.mode.starting_side,
            )
        self._pgn_offered_revision = None
        self._selected = None
        self._sounds.play(SoundEvent.GAME_START)
        self._refresh()

    def undo_move(self) -> None:
        if not self.service.can_undo():
            return
        self.service.undo()
        self._selected = None
        self._sounds.play(SoundEvent.UNDO)
        self._refresh()

    def reset_finished_game(self) -> bool:
        if self.service.status() not in _TERMINAL_STATUSES:
            self.status.setText("Игра ещё продолжается — клавиша R не сбрасывает позицию.")
            return False
        self.reset_game()
        return True

    def reload_piece_assets(self) -> None:
        self.board.invalidate_piece_renderers()
        self.white_pocket.invalidate_renderers()
        self.black_pocket.invalidate_renderers()
        self._refresh()

    def flip_board(self) -> None:
        self.board.flip_orientation()
        self._sync_seat_layout()

    def _sync_seat_layout(self) -> None:
        facing = bool(self._service and self._service.mode.facing_opponent)
        if facing and self.board.orientation is BoardOrientation.BLACK:
            top_clock, bottom_clock = self.white_clock, self.black_clock
            top_hand, bottom_hand = self.white_pocket, self.black_pocket
        else:
            top_clock, bottom_clock = self.black_clock, self.white_clock
            top_hand, bottom_hand = self.black_pocket, self.white_pocket

        capacity = 1
        columns = 3
        if self._service is not None:
            slots = hand_slot_types(self._service.mode)
            capacity = max(1, len(slots))
            columns = 3 if capacity >= 5 else 2
        for pocket in (self.white_pocket, self.black_pocket):
            pocket.set_capacity(capacity)
            pocket.set_grid(facing, columns=columns)
            pocket.set_rotate_pieces(False)
        top_hand.set_rotate_pieces(facing)

        _repack_column(self._clock_rail_layout, (top_clock, bottom_clock))
        if facing:
            self._top_bar.hide()
            self._bottom_bar.hide()
            self._hand_rail.show()
            _repack_column(self._hand_rail_layout, (top_hand, bottom_hand))
            _clear_layout(self._top_bar_layout)
            _clear_layout(self._bottom_bar_layout)
        else:
            self._hand_rail.hide()
            self._top_bar.show()
            self._bottom_bar.show()
            _clear_layout(self._hand_rail_layout)
            _repack_bar(self._top_bar_layout, top_hand)
            _repack_bar(self._bottom_bar_layout, bottom_hand)

    def _go_live(self) -> None:
        self.service.go_live()
        self._refresh()

    def _return_to_mainline(self) -> None:
        self.service.return_to_mainline()
        self._selected = None
        self._refresh()

    def copy_pgn(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(self.service.export_pgn())
        self.status.setText("PGN скопирован в буфер обмена.")

    def save_pgn(
        self,
        metadata: PgnMetadata,
        filename: str = "",
        *,
        storage: PgnStorage | None = None,
    ) -> Path:
        text = self.service.export_pgn(
            headers=metadata.headers(),
            result=metadata.result,
        )
        target = (storage or PgnStorage()).save(
            text,
            filename or metadata.suggested_filename(),
        )
        self.status.setText(f"PGN сохранён: {target}")
        return target

    def save_pgn_dialog(self) -> None:
        defaults = PgnMetadata(result=self._suggested_result())
        dialog = PgnSaveDialog(defaults, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.save_pgn(dialog.metadata(), dialog.requested_filename())
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Не удалось сохранить PGN", str(error))

    def _suggested_result(self) -> str:
        status = self.service.status()
        if status is GameStatus.STALEMATE:
            return "1/2-1/2"
        if status is GameStatus.CHECKMATE:
            return (
                "0-1"
                if self.service.state.side_to_move is PieceSide.WHITE
                else "1-0"
            )
        if status is GameStatus.VARIANT_WIN:
            return (
                "1-0"
                if self.service.state.side_to_move is PieceSide.WHITE
                else "0-1"
            )
        return "*"

    def _on_revision_selected(self, revision: int) -> None:
        self.service.go_to_revision(revision)
        self._selected = None
        self._refresh()

    def _navigate_revision(self, delta: int) -> None:
        current = self.service.record.view_revision
        target = min(
            self.service.record.live_revision,
            max(0, current + delta),
        )
        if target == current:
            return
        self.service.go_to_revision(target)
        self._selected = None
        self._refresh()

    def _quit(self) -> None:
        window = self.window()
        if window is not self:
            window.close()
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_square(self, index: int) -> None:
        if self._service is None or not self.service.can_play:
            return
        if self._service.status() in _TERMINAL_STATUSES:
            return
        if self.service.waiting_for_blocker:
            shape = self._service.mode.board.shape
            target = Square.from_index(index, shape.files, shape.ranks)
            try:
                side = self._service.state.side_to_move
                self.service.play_blocker(target)
                self._on_clock_after_move(side)
                self._sounds.play(SoundEvent.DUCK, accent=self._status_accent())
            except ValueError:
                self._sounds.play(SoundEvent.ILLEGAL)
            self._selected = None
            self._refresh()
            self._maybe_prompt_pgn_save()
            return
        if self.service.selected_hand_type is not None:
            shape = self._service.mode.board.shape
            target = Square.from_index(index, shape.files, shape.ranks)
            try:
                side = self._service.state.side_to_move
                self.service.play_selected_drop(target)
                self._on_clock_after_move(side)
                self._sounds.play(SoundEvent.DROP, accent=self._status_accent())
            except ValueError:
                self._sounds.play(SoundEvent.ILLEGAL)
            self._selected = None
            self._refresh()
            self._maybe_prompt_pgn_save()
            return
        view = self._service.visible_state()
        piece = view.board_state.piece_at(index)
        if self._selected is None:
            if piece is not None and piece.side is view.side_to_move:
                self._selected = index
                self._service.legal_moves_for_square(index)
                self._refresh()
            return
        if piece is not None and piece.side is view.side_to_move:
            self._selected = index
            self._service.legal_moves_for_square(index)
            self._refresh()
            return
        shape = self._service.mode.board.shape
        source = Square.from_index(self._selected, shape.files, shape.ranks)
        target = Square.from_index(index, shape.files, shape.ranks)
        candidates = [
            candidate
            for candidate in self._service.selected_moves
            if candidate.from_square == source and candidate.to_square == target
        ]
        move = _choose_move(candidates)
        if move is not None:
            before = self._service.visible_state()
            event = self._move_sound(before, move)
            side = before.side_to_move
            self._service.play_selected(move)
            if self._service.pending_move is None:
                self._on_clock_after_move(side)
            accent = None if self._service.pending_move is not None else self._status_accent()
            self._sounds.play(event, accent=accent)
        else:
            self._service.clear_selection()
            self._sounds.play(SoundEvent.ILLEGAL)
        self._selected = None
        self._refresh()
        self._maybe_prompt_pgn_save()

    def _on_pocket_piece(self, piece_type: str) -> None:
        if not self.service.can_play or self.service.status() in _TERMINAL_STATUSES:
            return
        sender = self.sender()
        if not isinstance(sender, PocketWidget) or sender.side is not self.service.state.side_to_move:
            return
        try:
            self.service.select_hand_piece(piece_type)
        except ValueError:
            self._sounds.play(SoundEvent.ILLEGAL)
            return
        self._selected = None
        self._refresh()

    def _move_sound(self, before: GameState, move: MoveAction) -> SoundEvent:
        files = before.board_state.board.shape.files
        source = before.board_state.piece_at(move.from_square.index(files))
        target = before.board_state.piece_at(move.to_square.index(files))
        if move.promotion_choice is not None:
            return SoundEvent.PROMOTE
        if (
            source is not None
            and source.piece_type.name == "king"
            and (
                abs(move.to_square.file - move.from_square.file) >= 2
                or (
                    target is not None
                    and target.piece_type.name == "rook"
                    and target.side is source.side
                )
            )
        ):
            return SoundEvent.CASTLE
        if target is not None and source is not None and target.side is not source.side:
            return SoundEvent.CAPTURE
        if (
            source is not None
            and source.piece_type.name == "pawn"
            and move.from_square.file != move.to_square.file
            and target is None
        ):
            return SoundEvent.CAPTURE
        return SoundEvent.MOVE

    def _status_accent(self) -> SoundEvent | None:
        status = self.service.status()
        if status is GameStatus.CHECKMATE:
            return SoundEvent.CHECKMATE
        if status is GameStatus.STALEMATE:
            return SoundEvent.STALEMATE
        if status is GameStatus.VARIANT_WIN:
            return SoundEvent.VARIANT_WIN
        if status is GameStatus.CHECK:
            return SoundEvent.CHECK
        return None

    def _on_clock_after_move(self, side: PieceSide) -> None:
        if self._clock_service is None:
            return
        self._clock_service.on_move_committed(side, 0)
        self._sync_clock_with_game()

    def _sync_clock_with_game(self) -> None:
        if self._clock_service is None or self._service is None:
            return
        if not self._service.is_live or self._service.status() in _TERMINAL_STATUSES:
            self._clock_service.pause()
        elif self._clock_service.is_paused:
            self._clock_service.resume()

    def _maybe_prompt_pgn_save(self) -> None:
        if self._service is None or self.service.status() not in _TERMINAL_STATUSES:
            return
        revision = self.service.record.live_revision
        if self._pgn_offered_revision == revision:
            return
        self._pgn_offered_revision = revision
        self._prompt_save_pgn()

    def _prompt_save_pgn(self) -> None:
        answer = QMessageBox.question(
            self,
            "Партия окончена",
            "Сохранить партию в PGN?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.save_pgn_dialog()

    def _tick_clock_display(self) -> None:
        if self._clock_service is None:
            return
        self._sync_clock_with_game()
        snapshot = self._clock_service.snapshot()
        self.white_clock.apply_snapshot(snapshot)
        self.black_clock.apply_snapshot(snapshot)
        self.clock_mode.setText(
            {
                TimeControlKind.SIMPLE: "Sudden death",
                TimeControlKind.FISCHER: "Fischer",
                TimeControlKind.BRONSTEIN: "Bronstein",
                TimeControlKind.BYOYOMI: "Byoyomi",
            }[snapshot.time_control.kind]
        )

    def _refresh(self) -> None:
        assert self._service is not None
        view = self._service.visible_state()
        position: dict[int, str] = {}
        for index, piece in view.board_state.cells.items():
            if piece is None:
                continue
            if piece.side is PieceSide.NEUTRAL:
                position[index] = "duck"
                continue
            position[index] = piece_svg_key(self._service.mode, piece)
        self.board.set_position(position)
        self._sync_clock_with_game()
        clock_visible = self._show_clock and self.service.is_live
        self._clock_rail.setVisible(clock_visible)
        self.clock_mode.setVisible(clock_visible)
        game_status = self._service.status()
        side = "белых" if view.side_to_move is PieceSide.WHITE else "чёрных"
        viewing = "" if self.service.is_live else " [архив]"
        pending = self.service.waiting_for_blocker
        mode_name = mode_display_name(getattr(self, "_mode_id", self.service.mode.id))
        if pending:
            status_text = f"{mode_name}: ход {side} — поставьте утку на пустую клетку"
            status_state = "active"
        elif self.service.pending_actions:
            status_text = f"{mode_name}: ход {side} — второй ход{viewing}"
            status_state = "active"
        else:
            status_text, status_state = {
                GameStatus.ACTIVE: (
                    f"{mode_name}: ход {side}{viewing}",
                    "active",
                ),
                GameStatus.CHECK: (
                    f"{mode_name}: ход {side} — шах{viewing}",
                    "check",
                ),
                GameStatus.CHECKMATE: (
                    f"Мат. Победили {'чёрные' if view.side_to_move is PieceSide.WHITE else 'белые'}.",
                    "mate",
                ),
                GameStatus.STALEMATE: ("Пат. Ничья.", "draw"),
                GameStatus.VARIANT_WIN: (f"Победили {side}.", "win"),
            }[game_status]
        self.status.setText(status_text)
        self.status.setProperty("state", status_state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._refresh_pockets()
        if self._timeline_per_ply:
            move_texts = self.service.record.timeline_log()
            revision_ranges = [
                (revision, revision)
                for revision in range(1, len(move_texts) + 1)
            ]
        else:
            rows = self.service.record.move_rows()
            move_texts = [text for text, _start, _end in rows]
            revision_ranges = [(start, end) for _text, start, end in rows]
        self.move_list.set_moves(
            move_texts,
            live_revision=self.service.record.live_revision,
            view_revision=self.service.record.view_revision,
            include_initial=self._include_initial_position,
            revision_ranges=revision_ranges,
        )
        self.live_button.setEnabled(not self.service.is_live)
        self.mainline_button.setVisible(self.service.in_variation)

        legal_destinations: set[int] = set()
        if self.service.can_play:
            shape = self._service.mode.board.shape
            if pending:
                legal_destinations = {
                    action.square.index(shape.files)
                    for action in self.service.legal_blocker_actions()
                }
            elif self.service.selected_hand_type is not None:
                legal_destinations = {
                    drop.to_square.index(shape.files)
                    for drop in self.service.selected_drops
                }
            elif self._selected is not None:
                legal_destinations = {
                    move.to_square.index(shape.files)
                    for move in self._service.selected_moves
                }
        check_squares: set[int] = set()
        if game_status in (GameStatus.CHECK, GameStatus.CHECKMATE):
            for index, piece in view.board_state.cells.items():
                if (
                    piece is not None
                    and piece.side is view.side_to_move
                    and self._service.mode.piece_is_royal(piece)
                ):
                    check_squares.add(index)
        self.board.set_highlights(
            selected=self._selected if self.service.can_play and not pending else None,
            legal_destinations=legal_destinations,
            check_squares=check_squares,
            last_move_squares=self._last_move_squares(),
            hint_squares=self._hint_squares(),
        )

    def _refresh_pockets(self) -> None:
        hands = self.service.state.hands
        show = hands is not None
        self.white_pocket.setVisible(show)
        self.black_pocket.setVisible(show)
        if not show:
            return
        to_move = self.service.state.side_to_move
        live = self.service.can_play and not self.service.waiting_for_blocker
        selected = self.service.selected_hand_type
        for widget in (self.white_pocket, self.black_pocket):
            widget.set_stacks(self._pocket_stacks(hands, widget.side))
            widget.set_interactive(live and widget.side is to_move)
            widget.set_selected(selected if widget.side is to_move else None)

    def _pocket_stacks(self, hands: HandsState, side: PieceSide) -> tuple[PocketStack, ...]:
        mode = self.service.mode
        counts: dict[str, int] = {}
        extras: list[str] = []
        drop_rule = mode.drop_rule
        face_groups: dict[frozenset[str], int] = {}
        for piece in hands.by_side.get(side, ()):
            name = piece.piece_type.name
            faces = None
            if drop_rule is not None:
                faces = drop_rule.allowed_faces(piece.piece_type)
            if faces:
                key = frozenset(faces)
                face_groups[key] = face_groups.get(key, 0) + 1
                continue
            if name not in counts:
                extras.append(name)
            counts[name] = counts.get(name, 0) + 1
        stacks: list[PocketStack] = []
        for faces, count in face_groups.items():
            for face in sorted(faces):
                stacks.append(
                    PocketStack(
                        piece_key=piece_svg_key_for(mode, face, side),
                        piece_type=face,
                        count=count,
                    )
                )
        order = list(
            shogi_hand_order()
            if mode.asset_family in FACING_ASSET_FAMILIES
            else _POCKET_ORDER
        )
        named = [name for name in order if name in counts] + [
            name for name in extras if name not in order
        ]
        for name in named:
            stacks.append(
                PocketStack(
                    piece_key=piece_svg_key_for(mode, name, side),
                    piece_type=name,
                    count=counts[name],
                )
            )
        return tuple(stacks)

    def _last_move_squares(self) -> set[int]:
        files = self.service.mode.board.shape.files
        squares: set[int] = set()
        pending = self.service.pending_move
        if pending is not None:
            squares.add(pending.from_square.index(files))
            squares.add(pending.to_square.index(files))
        revision = self.service.record.view_revision
        turns = self.service.record.turns
        if revision <= 0 or revision > len(turns):
            return squares
        for action in turns[revision - 1].turn.actions:
            if isinstance(action, MoveAction):
                squares.add(action.from_square.index(files))
                squares.add(action.to_square.index(files))
            elif isinstance(action, DropAction):
                squares.add(action.to_square.index(files))
            elif isinstance(action, PlaceBlockerAction):
                squares.add(action.square.index(files))
        return squares

    def _hint_squares(self) -> set[int]:
        squares: set[int] = set()
        cell_count = self.service.mode.board.shape.cell_count
        for condition in self.service.mode.victory_conditions():
            if condition.kind is not VictoryKind.KING_REACHES_ZONE:
                continue
            mask = condition.target_zone_mask
            if not mask:
                continue
            for index in range(cell_count):
                if mask & (1 << index):
                    squares.add(index)
        return squares


def _clear_layout(layout: QHBoxLayout | QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)


def _repack_column(layout: QVBoxLayout, widgets: tuple[QWidget, QWidget]) -> None:
    _clear_layout(layout)
    layout.addWidget(widgets[0], 0, Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch(1)
    layout.addWidget(widgets[1], 0, Qt.AlignmentFlag.AlignHCenter)


def _repack_bar(layout: QHBoxLayout, pocket: QWidget) -> None:
    _clear_layout(layout)
    layout.addStretch(1)
    layout.addWidget(pocket)
    layout.addStretch(1)


def _choose_move(candidates: list) -> MoveAction | None:
    if not candidates:
        return None
    promoted = [move for move in candidates if move.promotion_choice is not None]
    queen = next(
        (
            move
            for move in promoted
            if move.promotion_choice is not None and move.promotion_choice.name == "queen"
        ),
        None,
    )
    if queen is not None:
        return queen
    plain = [move for move in candidates if move.promotion_choice is None]
    shift = bool(
        QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
    )
    if shift and promoted:
        return promoted[0]
    if plain:
        return plain[0]
    if promoted:
        return promoted[0]
    return candidates[0]
