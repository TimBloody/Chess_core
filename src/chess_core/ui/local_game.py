"""Thin PyQt adapter for a local game service."""

from __future__ import annotations

import time
from collections.abc import Callable

from PyQt6.QtCore import QTimer
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
from chess_core.ui.widgets.board_widget import BoardWidget
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget

_ASSET_NAMES = {
    "king": "K",
    "queen": "Q",
    "rook": "R",
    "bishop": "B",
    "knight": "N",
    "pawn": "P",
}

_TERMINAL_STATUSES = frozenset((GameStatus.CHECKMATE, GameStatus.STALEMATE))


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
        self.move_list = MoveListWidget()
        self.clock_widget = GameClockWidget()
        self.evaluation_bar = EvaluationBarWidget()
        self.instructions = QLabel(
            "Ход: щёлкните фигуру и клетку. F — перевернуть доску; "
            "Ctrl+Z — отмена хода; R — новая игра после окончания."
        )
        self.new_game_button = QPushButton("Новая игра / Сброс")
        self.live_button = QPushButton("К текущей позиции")
        self.quit_button = QPushButton("Выйти")

        main_split = QSplitter()
        board_panel = QWidget()
        board_layout = QVBoxLayout(board_panel)
        board_layout.addWidget(self.status)
        board_layout.addWidget(self.board)
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
        sidebar_layout.addWidget(QLabel("Запись партии"))
        sidebar_layout.addWidget(self.move_list)

        main_split.addWidget(board_panel)
        main_split.addWidget(sidebar)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(main_split)

        self.board.square_clicked.connect(self._on_square)
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
        self._service = LocalGameService(mode)
        self._clock_service = GameClockService(TimeControlConfig.blitz(), _MonoClock())
        self._selected = None
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
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

    def _on_square(self, index: int) -> None:
        if self._service is None or not self.service.is_live:
            return
        if self._service.status() in (GameStatus.CHECKMATE, GameStatus.STALEMATE):
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
        move = next(
            (
                candidate
                for candidate in candidates
                if candidate.promotion_choice is not None
                and candidate.promotion_choice.name == "queen"
            ),
            candidates[0] if candidates else None,
        )
        if move is not None:
            side = self._service.state.side_to_move
            self._service.play_selected(move)
            if self._clock_service is not None:
                self._clock_service.on_move_committed(side, 0)
        else:
            self._service.clear_selection()
        self._selected = None
        self._refresh()

    def _tick_clock_display(self) -> None:
        if self._clock_service is None:
            return
        self.clock_widget.set_snapshot(
            self._clock_service.snapshot(),
            client_mono_ms=_MonoClock().now_ms(),
        )

    def _refresh(self) -> None:
        assert self._service is not None
        position: dict[int, str] = {}
        for index, piece in self._service.state.board_state.cells.items():
            if piece is None or piece.side is PieceSide.NEUTRAL:
                continue
            symbol = _ASSET_NAMES.get(piece.piece_type.name)
            if symbol is not None:
                position[index] = ("w" if piece.side is PieceSide.WHITE else "b") + symbol
        self.board.set_position(position)
        game_status = self._service.status()
        side = "белых" if self._service.state.side_to_move is PieceSide.WHITE else "чёрных"
        viewing = "" if self.service.is_live else " [архив]"
        status_text = {
            GameStatus.ACTIVE: f"Ход {side} — игра продолжается{viewing}",
            GameStatus.CHECK: f"Ход {side} — шах{viewing}",
            GameStatus.CHECKMATE: (
                f"Мат. Победили {'чёрные' if self._service.state.side_to_move is PieceSide.WHITE else 'белые'}."
            ),
            GameStatus.STALEMATE: "Пат. Ничья.",
        }[game_status]
        self.status.setText(status_text)
        self.move_list.set_moves(
            self.service.move_log,
            live_revision=self.service.record.live_revision,
            view_revision=self.service.record.view_revision,
        )
        self.live_button.setEnabled(not self.service.is_live)

        legal_destinations: set[int] = set()
        if self._selected is not None and self.service.is_live:
            shape = self._service.mode.board.shape
            legal_destinations = {
                move.to_square.index(shape.files)
                for move in self._service.selected_moves
            }
        check_squares: set[int] = set()
        if game_status in (GameStatus.CHECK, GameStatus.CHECKMATE):
            for index, piece in self._service.state.board_state.cells.items():
                if (
                    piece is not None
                    and piece.side is self._service.state.side_to_move
                    and piece.piece_type.name == "king"
                ):
                    check_squares.add(index)
        self.board.set_highlights(
            selected=self._selected if self.service.is_live else None,
            legal_destinations=legal_destinations,
            check_squares=check_squares,
        )
