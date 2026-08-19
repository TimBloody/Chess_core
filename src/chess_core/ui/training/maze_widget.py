"""Maze training UI: capture every black piece, white dots are obstacles."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.training.maze import (
    MAZE_HERO_TYPES,
    MazeMoveResult,
    MazeSession,
    MazeStatus,
    generate_maze,
)
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import default_registry
from chess_core.modes.chess import classic_chess
from chess_core.ui.piece_assets import piece_svg_key
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget

_PIECE_LABELS = {
    "knight": "Конь",
    "bishop": "Слон",
    "rook": "Ладья",
    "queen": "Ферзь",
    "king": "Король",
}


class MazeTrainingWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._session: MazeSession | None = None
        self._mode = classic_chess()

        self.piece_combo = QComboBox()
        for piece_type in MAZE_HERO_TYPES:
            self.piece_combo.addItem(_PIECE_LABELS[piece_type], piece_type)
        self.targets_spin = QSpinBox()
        self.targets_spin.setRange(1, 8)
        self.targets_spin.setValue(4)
        self.obstacles_spin = QSpinBox()
        self.obstacles_spin.setRange(0, 24)
        self.obstacles_spin.setValue(8)
        self.avoid_checks = QCheckBox("Нельзя вставать под бой")
        self.start_button = QPushButton("Новый лабиринт")
        self.status = QLabel("Съездите все чёрные фигуры. Белые точки — препятствия.")
        self.status.setObjectName("gameStatus")
        self.status.setWordWrap(True)
        self.hint = QLabel(
            "Как в Train with Magnus: белая фигура ходит своими ходами, "
            "чёрные стоят на месте. Усложнение запрещает клетки под боем."
        )
        self.hint.setObjectName("gameHint")
        self.hint.setWordWrap(True)
        self.board = BoardWidget()
        self.board.set_orientation(BoardOrientation.WHITE)

        controls = QHBoxLayout()
        for label, widget in (
            ("Фигура", self.piece_combo),
            ("Чёрных фигур", self.targets_spin),
            ("Препятствий", self.obstacles_spin),
        ):
            box = QVBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("panelTitle")
            box.addWidget(caption)
            box.addWidget(widget)
            controls.addLayout(box)
        controls.addWidget(self.avoid_checks, alignment=Qt.AlignmentFlag.AlignBottom)
        controls.addStretch()
        controls.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignBottom)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.board, 1)
        layout.addWidget(self.hint)

        self.start_button.clicked.connect(self.start_round)
        self.board.square_clicked.connect(self._on_square)

    def start_round(self) -> None:
        piece_type = self.piece_combo.currentData()
        if piece_type not in MAZE_HERO_TYPES:
            piece_type = "knight"
        puzzle = generate_maze(
            piece_type=piece_type,
            target_count=self.targets_spin.value(),
            obstacle_count=self.obstacles_spin.value(),
            avoid_checks=self.avoid_checks.isChecked(),
        )
        self._session = MazeSession.start(puzzle, self._mode)
        remaining = len(self._session.remaining)
        self.status.setText(f"Съесть чёрных фигур: {remaining}")
        self.status.setProperty("state", "active")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._refresh()

    def reload_piece_assets(self) -> None:
        self.board.invalidate_piece_renderers()
        self._refresh()

    def _on_square(self, index: int) -> None:
        session = self._session
        if session is None or session.status is not MazeStatus.PLAYING:
            return
        if index == session.hero_square:
            self._refresh()
            return
        result = session.try_move(index)
        if result is MazeMoveResult.ILLEGAL:
            self.status.setText("Сюда эта фигура не ходит.")
            self.status.setProperty("state", "active")
        elif result is MazeMoveResult.UNDER_FIRE:
            self.status.setText("Под боем стоять нельзя.")
            self.status.setProperty("state", "check")
        elif result is MazeMoveResult.WON:
            self.status.setText(f"Лабиринт пройден за {session.move_count} ходов.")
            self.status.setProperty("state", "win")
        elif result is MazeMoveResult.STUCK:
            self.status.setText("Ходов больше нет. Начните новый лабиринт.")
            self.status.setProperty("state", "draw")
        elif result is MazeMoveResult.CAPTURED:
            self.status.setText(f"Съесть чёрных фигур: {len(session.remaining)}")
            self.status.setProperty("state", "active")
        else:
            self.status.setText(f"Съесть чёрных фигур: {len(session.remaining)}")
            self.status.setProperty("state", "active")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._refresh()

    def _refresh(self) -> None:
        session = self._session
        if session is None:
            self.board.set_shape(8, 8)
            self.board.set_position({})
            self.board.clear_highlights()
            return
        puzzle = session.puzzle
        self.board.set_shape(puzzle.files, puzzle.ranks)
        position: dict[int, str] = {
            session.hero_square: piece_svg_key(
                self._mode,
                Piece(PieceTypeId(puzzle.piece_type), PieceSide.WHITE),
            )
        }
        for index, type_name in session.remaining.items():
            position[index] = piece_svg_key(
                self._mode, Piece(PieceTypeId(type_name), PieceSide.BLACK)
            )
        self.board.set_position(position)
        self.board.set_highlights(
            selected=session.hero_square,
            legal_destinations=session.legal_destinations(),
            last_move_squares=(session.hero_square,),
            dot_squares=puzzle.obstacles,
        )
        self.board.setCursor(Qt.CursorShape.PointingHandCursor)
