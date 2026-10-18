"""Maze training UI: capture every black piece; yellow dots are obstacles."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
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
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import classic_chess
from chess_core.ui.piece_keys import piece_asset_key
from chess_core.ui.theme import tighten_wrapping_label
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget

_PIECE_LABELS = {
    "knight": "Конь",
    "bishop": "Слон",
    "rook": "Ладья",
    "queen": "Ферзь",
    "king": "Король",
}


class MazeTrainingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session: MazeSession | None = None
        self._mode = classic_chess()
        self._hint_this_ply = False

        self.piece_combo = QComboBox()
        self.piece_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.piece_combo.setMinimumContentsLength(8)
        for piece_type in MAZE_HERO_TYPES:
            self.piece_combo.addItem(_PIECE_LABELS[piece_type], piece_type)
        self.targets_spin = QSpinBox()
        self.targets_spin.setRange(1, 8)
        self.targets_spin.setValue(4)
        self.obstacles_spin = QSpinBox()
        self.obstacles_spin.setRange(0, 20)
        self.obstacles_spin.setValue(8)
        self.avoid_checks = QCheckBox("Нельзя вставать под бой")
        self.avoid_checks.setChecked(True)
        self.start_button = QPushButton("Новый лабиринт")
        self.undo_button = QPushButton("Отмена хода")
        self.undo_button.setEnabled(False)
        self.reset_button = QPushButton("Заново")
        self.reset_button.setEnabled(False)
        self.status = QLabel("Нажмите «Новый лабиринт», чтобы начать.")
        self.status.setObjectName("gameStatus")
        tighten_wrapping_label(self.status)
        self.hint = QLabel(
            "Каждым ходом белая фигура берёт чёрную. Съесть часто можно "
            "несколько, но порядок важен: неверный ход ставит под бой или "
            "отрезает путь. Подсказка (возможные взятия) появляется только "
            "если кликнуть клетку, куда фигура пойти не может — и только на "
            "этот ход. Жёлтые точки — препятствия. F — перевернуть доску."
        )
        self.hint.setObjectName("gameHint")
        tighten_wrapping_label(self.hint)
        self.board = BoardWidget()
        self.board.set_orientation(BoardOrientation.WHITE)
        self.board.set_coordinates_visible(True)
        self.board.setCursor(Qt.CursorShape.PointingHandCursor)

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
        controls.addWidget(self.undo_button, alignment=Qt.AlignmentFlag.AlignBottom)
        controls.addWidget(self.reset_button, alignment=Qt.AlignmentFlag.AlignBottom)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.board, 1)
        layout.addWidget(self.hint)

        self.start_button.clicked.connect(self.start_round)
        self.undo_button.clicked.connect(self._undo)
        self.reset_button.clicked.connect(self._reset)
        self.board.square_clicked.connect(self._on_square)
        self._flip_shortcut = QShortcut(QKeySequence("F"), self)
        self._flip_shortcut.activated.connect(self.board.flip_orientation)
        self._undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._undo)
        self.start_round()

    def reload_piece_assets(self) -> None:
        self.board.invalidate_renderers()
        self._refresh()

    def start_round(self) -> None:
        piece_type = self.piece_combo.currentData()
        if piece_type not in MAZE_HERO_TYPES:
            piece_type = "knight"
        try:
            puzzle = generate_maze(
                piece_type=piece_type,
                target_count=self.targets_spin.value(),
                obstacle_count=self.obstacles_spin.value(),
                avoid_checks=self.avoid_checks.isChecked(),
            )
        except (RuntimeError, ValueError):
            self._session = None
            self._set_status("Не удалось собрать лабиринт. Уменьшите сложность.", "mate")
            self._refresh()
            return
        self._session = MazeSession.start(puzzle, self._mode)
        self._hint_this_ply = False
        self._set_status(self._playing_text(), "active")
        self._refresh()

    def _undo(self) -> None:
        session = self._session
        if session is None or not session.undo():
            return
        self._hint_this_ply = False
        self._set_status(self._playing_text(), "active")
        self._refresh()

    def _reset(self) -> None:
        session = self._session
        if session is None:
            return
        session.reset()
        self._hint_this_ply = False
        self._set_status(self._playing_text(), "active")
        self._refresh()

    def _on_square(self, index: int) -> None:
        session = self._session
        if session is None or session.status is not MazeStatus.PLAYING:
            return
        if index == session.hero_square:
            self._hint_this_ply = False
            self._refresh()
            return
        result = session.try_move(index)
        if result is MazeMoveResult.ILLEGAL:
            self._hint_this_ply = True
            if session.puzzle.captures_only and index not in session.remaining:
                self._set_status("Каждым ходом нужно взять фигуру.", "active")
            else:
                self._set_status("Сюда эта фигура не ходит.", "active")
        elif result is MazeMoveResult.UNDER_FIRE:
            self._hint_this_ply = True
            self._set_status("Под боем стоять нельзя.", "check")
        elif result is MazeMoveResult.WON:
            self._hint_this_ply = False
            self._set_status(
                f"Лабиринт пройден за {session.move_count} ходов.", "win"
            )
        elif result is MazeMoveResult.STUCK:
            self._hint_this_ply = False
            self._set_status("Ходов больше нет. Начните новый лабиринт.", "draw")
        else:
            self._hint_this_ply = False
            self._set_status(self._playing_text(), "active")
        self._refresh()

    def _playing_text(self) -> str:
        session = self._session
        if session is None:
            return "Нажмите «Новый лабиринт», чтобы начать."
        if session.status is MazeStatus.WON:
            return f"Лабиринт пройден за {session.move_count} ходов."
        if session.status is MazeStatus.STUCK:
            return "Ходов больше нет. Начните новый лабиринт."
        remaining = len(session.remaining)
        moves = session.move_count
        if moves:
            return f"Осталось взять: {remaining}. Ходов: {moves}."
        return f"Осталось взять: {remaining}. Порядок важен."

    def _set_status(self, text: str, state: str) -> None:
        self.status.setText(text)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _refresh(self) -> None:
        session = self._session
        self.undo_button.setEnabled(bool(session is not None and session.can_undo))
        self.reset_button.setEnabled(session is not None)
        if session is None:
            self.board.set_shape(8, 8)
            self.board.set_position({})
            self.board.clear_highlights()
            return
        puzzle = session.puzzle
        self.board.set_shape(puzzle.files, puzzle.ranks)
        position: dict[int, str] = {}
        hero_key = piece_asset_key(
            Piece(PieceTypeId(puzzle.piece_type), PieceSide.WHITE),
            self._mode.asset_family,
        )
        if hero_key is not None:
            position[session.hero_square] = hero_key
        for index, type_name in session.remaining.items():
            key = piece_asset_key(
                Piece(PieceTypeId(type_name), PieceSide.BLACK),
                self._mode.asset_family,
            )
            if key is not None:
                position[index] = key
        for index in puzzle.obstacles:
            position[index] = "blocker"
        self.board.set_position(position)
        legal: set[int] = set()
        blocked: set[int] = set()
        if (
            self._hint_this_ply
            and session.status is MazeStatus.PLAYING
        ):
            legal = session.legal_destinations()
            blocked = session.capture_destinations() - legal
        self.board.set_highlights(
            selected=session.hero_square if session.status is MazeStatus.PLAYING else None,
            legal_destinations=legal,
            blocked_squares=blocked,
        )
