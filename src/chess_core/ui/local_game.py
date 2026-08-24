"""Thin PyQt adapter for a local game service."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.clock import GameClockService
from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig
from chess_core.ui.piece_keys import droppable_type_names, piece_asset_key
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketWidget

_TERMINAL_STATUSES = frozenset(
    (
        GameStatus.CHECKMATE,
        GameStatus.STALEMATE,
        GameStatus.MATERIAL_WIN,
        GameStatus.TRY_WIN,
        GameStatus.KING_CAPTURE_WIN,
    )
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
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._service: LocalGameService | None = None
        self._selected: int | None = None
        self._clock_service: GameClockService | None = None
        self.board = BoardWidget()
        self.status = QLabel()
        self.status.setObjectName("gameStatus")
        self.move_list = MoveListWidget()
        self.clock_widget = GameClockWidget()
        self.evaluation_bar = EvaluationBarWidget()
        self.instructions = QLabel(
            "Ход: щёлкните фигуру и клетку. F — перевернуть доску; "
            "Ctrl+Z — отмена хода; R — новая игра после окончания."
        )
        self.instructions.setObjectName("gameHint")
        self.black_pocket = PocketWidget(PieceSide.BLACK)
        self.white_pocket = PocketWidget(PieceSide.WHITE)
        self._hand_rail = QWidget()
        self._hand_rail_layout = QVBoxLayout(self._hand_rail)
        self._hand_rail_layout.setContentsMargins(0, 0, 0, 0)
        self._hand_rail.hide()
        self.new_game_button = QPushButton("Новая игра / Сброс")
        self.live_button = QPushButton("К текущей позиции")
        self.quit_button = QPushButton("Выйти")

        main_split = QSplitter()
        board_panel = QWidget()
        board_layout = QVBoxLayout(board_panel)
        board_row = QWidget()
        board_row_layout = QHBoxLayout(board_row)
        board_row_layout.setContentsMargins(0, 0, 0, 0)
        board_row_layout.addWidget(self.board, 1)
        board_row_layout.addWidget(self._hand_rail, 0, Qt.AlignmentFlag.AlignVCenter)
        board_layout.addWidget(self.status)
        board_layout.addWidget(board_row, 1)
        board_layout.addWidget(self.instructions)
        controls = QHBoxLayout()
        controls.addWidget(self.new_game_button)
        controls.addWidget(self.live_button)
        controls.addStretch()
        controls.addWidget(self.quit_button)
        board_layout.addLayout(controls)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(self.clock_widget)
        sidebar_layout.addWidget(self.evaluation_bar)
        log_title = QLabel("Запись партии")
        log_title.setObjectName("panelTitle")
        sidebar_layout.addWidget(log_title)
        sidebar_layout.addWidget(self.move_list)

        main_split.addWidget(board_panel)
        main_split.addWidget(sidebar)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(main_split)

        self.board.square_clicked.connect(self._on_square)
        self.white_pocket.piece_chosen.connect(self._on_pocket)
        self.black_pocket.piece_chosen.connect(self._on_pocket)
        self.new_game_button.clicked.connect(self.reset_game)
        self.live_button.clicked.connect(self._go_live)
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

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._tick_clock_display)
        self._ui_timer.start()

        self.set_mode(mode_id)

    def set_mode(self, mode_id: str) -> None:
        mode = self._resolve(mode_id)
        if str(mode.initial_extras.get("match_kind", "single")) in {"bughouse", "hand_and_brain"}:
            self._service = LocalGameService(mode)
            self._clock_service = GameClockService(TimeControlConfig.blitz(), _MonoClock())
            self._selected = None
            self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
            self.status.setText(
                "Этот режим рассчитан на 4 клиента в сети. Откройте вкладку «Сеть»."
            )
            self.board.set_position({})
            self.board.clear_highlights()
            self._hide_hands()
            self.clock_widget.setVisible(False)
            return
        self._service = LocalGameService(mode)
        self._clock_service = GameClockService(TimeControlConfig.blitz(), _MonoClock())
        self._selected = None
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
        self.clock_widget.setVisible(True)
        self._refresh()

    def load_position(self, state: GameState) -> None:
        self.service.load_position(state)
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
            )
        self._selected = None
        self._refresh()

    def undo_move(self) -> None:
        if not self.service.can_undo():
            return
        self.service.undo()
        self._selected = None
        self._refresh()

    def reset_finished_game(self) -> bool:
        if self.service.status() not in _TERMINAL_STATUSES:
            self.status.setText("Игра ещё продолжается — клавиша R не сбрасывает позицию.")
            return False
        self.reset_game()
        return True

    def flip_board(self) -> None:
        self.board.flip_orientation()
        self._layout_hands()
        self._refresh()

    def _go_live(self) -> None:
        self.service.go_live()
        self._refresh()

    def _on_revision_selected(self, revision: int) -> None:
        self.service.go_to_revision(revision)
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

    @property
    def pocket(self) -> PocketWidget:
        if self._service is not None and self._service.state.side_to_move is PieceSide.BLACK:
            return self.black_pocket
        return self.white_pocket

    def _on_pocket(self, piece_type: str) -> None:
        if self._service is None or not self.service.is_live:
            return
        sender = self.sender()
        if isinstance(sender, PocketWidget) and sender.side is not self.service.state.side_to_move:
            sender.clear_selection()
            return
        other = self.black_pocket if self.pocket is self.white_pocket else self.white_pocket
        other.clear_selection()
        self._selected = None
        self._service.clear_selection()
        self._refresh()

    def _on_square(self, index: int) -> None:
        if self._service is None or not self.service.is_live:
            return
        if self._service.status() in _TERMINAL_STATUSES:
            return
        if self.pocket.selected_type() is not None:
            self._try_drop(index)
            return
        piece = self._service.state.board_state.piece_at(index)
        if self._selected is None:
            if piece is not None and piece.side is self._service.state.side_to_move:
                self._selected = index
                self._service.legal_moves_for_square(index)
                self._refresh()
            return
        if piece is not None and piece.side is self._service.state.side_to_move:
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
        move = _prefer_promotion(candidates)
        if move is not None:
            self._commit_side(lambda: self._service.play_selected(move))
        else:
            self._service.clear_selection()
        self._selected = None
        self._refresh()

    def _try_drop(self, index: int) -> None:
        name = self.pocket.selected_type()
        if name is None or self._service is None:
            return
        shape = self._service.mode.board.shape
        target = Square.from_index(index, shape.files, shape.ranks)
        drop = next(
            (
                action
                for action in self._service.legal_drops()
                if action.piece_type.name == name and action.to_square == target
            ),
            None,
        )
        if drop is not None:
            self._commit_side(lambda: self._service.play_action(drop))
        self.pocket.clear_selection()
        self._selected = None
        self._refresh()

    def _commit_side(self, play) -> None:
        assert self._service is not None
        side = self._service.state.side_to_move
        play()
        if self._clock_service is not None:
            self._clock_service.on_move_committed(side, 0)

    def _tick_clock_display(self) -> None:
        if self._clock_service is None:
            return
        self.clock_widget.set_snapshot(
            self._clock_service.snapshot(),
            client_mono_ms=_MonoClock().now_ms(),
        )

    def _sync_clock_with_game(self) -> None:
        if self._clock_service is None:
            return
        terminal = self.service.status() in _TERMINAL_STATUSES
        viewing_archive = not self.service.is_live
        if terminal or viewing_archive:
            if not self._clock_service.is_paused:
                self._clock_service.pause()
            self.clock_widget.setVisible(not viewing_archive)
        else:
            if self._clock_service.is_paused:
                self._clock_service.resume()
            self.clock_widget.setVisible(True)
        self._tick_clock_display()

    def _refresh(self) -> None:
        assert self._service is not None
        family = self._service.mode.asset_family
        position: dict[int, str] = {}
        for index, piece in self._service.state.board_state.cells.items():
            if piece is None or piece.side is PieceSide.NEUTRAL:
                continue
            key = piece_asset_key(piece, family)
            if key is not None:
                position[index] = key
        self.board.set_position(position)
        game_status = self._service.status()
        self.status.setText(_status_text(self._service, game_status))
        self.status.setProperty("state", _status_state(game_status))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._sync_clock_with_game()
        self.move_list.set_moves(
            self.service.move_log,
            live_revision=self.service.record.live_revision,
            view_revision=self.service.record.view_revision,
        )
        self.live_button.setEnabled(not self.service.is_live)
        self._refresh_pocket()

        legal_destinations: set[int] = set()
        shape = self._service.mode.board.shape
        if self._selected is not None and self.service.is_live:
            legal_destinations = {
                move.to_square.index(shape.files)
                for move in self._service.selected_moves
            }
        elif self.pocket.selected_type() is not None and self.service.is_live:
            name = self.pocket.selected_type()
            legal_destinations = {
                action.to_square.index(shape.files)
                for action in self._service.legal_drops()
                if action.piece_type.name == name
            }
        check_squares: set[int] = set()
        if game_status in (GameStatus.CHECK, GameStatus.CHECKMATE):
            royal = self._service.mode.royal_type
            for index, piece in self._service.state.board_state.cells.items():
                if (
                    piece is not None
                    and piece.side is self._service.state.side_to_move
                    and piece.piece_type.name == royal
                ):
                    check_squares.add(index)
        self.board.set_highlights(
            selected=self._selected if self.service.is_live else None,
            legal_destinations=legal_destinations,
            check_squares=check_squares,
        )

    def _hide_hands(self) -> None:
        self._hand_rail.hide()
        for pocket in (self.white_pocket, self.black_pocket):
            pocket.setVisible(False)
            pocket.clear_selection()

    def _layout_hands(self) -> None:
        layout = self._hand_rail_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self._hand_rail)
        flipped = self.board.orientation is BoardOrientation.BLACK
        top = self.white_pocket if flipped else self.black_pocket
        bottom = self.black_pocket if flipped else self.white_pocket
        layout.addWidget(top, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addStretch()
        layout.addWidget(bottom, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

    def _refresh_pocket(self) -> None:
        assert self._service is not None
        has_drops = self._service.mode.drop_rule is not None
        if not has_drops:
            self._hide_hands()
            return
        types = droppable_type_names(self._service.mode)
        family = self._service.mode.asset_family
        live = self.service.is_live and self._service.status() not in _TERMINAL_STATUSES
        mover = self._service.state.side_to_move
        for pocket in (self.white_pocket, self.black_pocket):
            pocket.setVisible(True)
            pocket.set_hands(
                self._service.state.hands,
                pocket.side,
                enabled=live and pocket.side is mover,
                types=types,
                asset_family=family,
                grid=True,
            )
        self._layout_hands()
        self._hand_rail.show()


def _prefer_promotion(candidates):
    queen = next(
        (
            candidate
            for candidate in candidates
            if candidate.promotion_choice is not None
            and candidate.promotion_choice.name == "queen"
        ),
        None,
    )
    if queen is not None:
        return queen
    promoted = next(
        (candidate for candidate in candidates if candidate.promotion_choice is not None),
        None,
    )
    return promoted or (candidates[0] if candidates else None)


def _status_text(service: LocalGameService, game_status: GameStatus) -> str:
    side = "белых" if service.state.side_to_move is PieceSide.WHITE else "чёрных"
    viewing = "" if service.is_live else " [архив]"
    previous = "чёрные" if service.state.side_to_move is PieceSide.WHITE else "белые"
    if game_status is GameStatus.ACTIVE:
        return f"Ход {side} — игра продолжается{viewing}"
    if game_status is GameStatus.CHECK:
        return f"Ход {side} — шах{viewing}"
    if game_status is GameStatus.CHECKMATE:
        return f"Мат. Победили {previous}."
    if game_status is GameStatus.STALEMATE:
        return "Пат. Ничья."
    if game_status is GameStatus.TRY_WIN:
        return f"Победили {previous}: королевская фигура достигла зоны."
    if game_status is GameStatus.KING_CAPTURE_WIN:
        return f"Победили {previous}: королевская фигура взята."
    white = sum(
        1
        for piece in service.state.board_state.cells.values()
        if piece is not None and piece.side is PieceSide.WHITE
    )
    black = sum(
        1
        for piece in service.state.board_state.cells.values()
        if piece is not None and piece.side is PieceSide.BLACK
    )
    if white == 0:
        return "Победили белые: не осталось фигур."
    if black == 0:
        return "Победили чёрные: не осталось фигур."
    mover = "белые" if service.state.side_to_move is PieceSide.WHITE else "чёрные"
    return f"Победили {mover}: нет легальных ходов."


def _status_state(game_status: GameStatus) -> str:
    if game_status is GameStatus.CHECK:
        return "check"
    if game_status is GameStatus.CHECKMATE:
        return "mate"
    if game_status is GameStatus.STALEMATE:
        return "draw"
    if game_status in (
        GameStatus.MATERIAL_WIN,
        GameStatus.TRY_WIN,
        GameStatus.KING_CAPTURE_WIN,
    ):
        return "win"
    return "active"

