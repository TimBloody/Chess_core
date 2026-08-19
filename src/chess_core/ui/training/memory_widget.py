"""Memory training UI: shape, sequence, and position reconstruction."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.training.memory import (
    MemoryFormat,
    PositionMemoryService,
    SequenceMemoryService,
    SequencePrompt,
    ShapeMemoryService,
    ShapePrompt,
)
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.core.state import GameState
from chess_core.ui.editor import EditorWidget
from chess_core.ui.piece_assets import piece_svg_key
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget


class _Phase(Enum):
    IDLE = auto()
    PREVIEW = auto()
    INPUT = auto()
    DONE = auto()


_FORMAT_LABELS = {
    MemoryFormat.SHAPE: "Фигура на поле",
    MemoryFormat.SEQUENCE: "Последовательность клеток",
    MemoryFormat.POSITION: "Шахматная позиция",
}


class MemoryTrainingWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        mode_id: str = "chess",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._mode_id = mode_id
        self._shapes = ShapeMemoryService()
        self._sequences = SequenceMemoryService()
        self._positions = PositionMemoryService()
        self._phase = _Phase.IDLE
        self._shape_prompt: ShapePrompt | None = None
        self._sequence_prompt: SequencePrompt | None = None
        self._position_target: GameState | None = None
        self._attempt: list[int] = []
        self._preview_index = 0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timer)

        self.format_combo = QComboBox()
        for fmt, label in _FORMAT_LABELS.items():
            self.format_combo.addItem(label, fmt)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(3, 8)
        self.size_spin.setValue(4)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(2, 32)
        self.count_spin.setValue(5)
        self.reveal_spin = QSpinBox()
        self.reveal_spin.setRange(500, 12000)
        self.reveal_spin.setSingleStep(250)
        self.reveal_spin.setValue(2500)
        self.reveal_spin.setSuffix(" мс")
        self.start_button = QPushButton("Новый раунд")
        self.check_button = QPushButton("Проверить")
        self.check_button.setEnabled(False)
        self.status = QLabel("Выберите формат и нажмите «Новый раунд».")
        self.status.setObjectName("gameStatus")
        self.status.setWordWrap(True)
        self.hint = QLabel()
        self.hint.setObjectName("gameHint")
        self.hint.setWordWrap(True)

        self.board = BoardWidget()
        self.board.set_coordinates_visible(False)
        self.editor = EditorWidget(
            mode_resolver,
            mode_id,
            require_one_king_per_side=False,
            enable_play=False,
        )
        self._pages = QStackedWidget()
        self._pages.addWidget(self.board)
        self._pages.addWidget(self.editor)

        controls = QHBoxLayout()
        for label, widget in (
            ("Формат", self.format_combo),
            ("Размер", self.size_spin),
            ("Сложность", self.count_spin),
            ("Показ", self.reveal_spin),
        ):
            box = QVBoxLayout()
            caption = QLabel(label)
            caption.setObjectName("panelTitle")
            box.addWidget(caption)
            box.addWidget(widget)
            controls.addLayout(box)
        controls.addStretch()
        controls.addWidget(self.start_button, alignment=Qt.AlignmentFlag.AlignBottom)
        controls.addWidget(self.check_button, alignment=Qt.AlignmentFlag.AlignBottom)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self._pages, 1)
        layout.addWidget(self.hint)

        self.format_combo.currentIndexChanged.connect(self._sync_controls)
        self.start_button.clicked.connect(self.start_round)
        self.check_button.clicked.connect(self._check)
        self.board.square_clicked.connect(self._on_square)
        self._sync_controls()
        self._apply_grid_board()

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        self.editor.set_mode(mode_id)
        if self._current_format() is MemoryFormat.POSITION:
            self._reset_idle()

    def reload_piece_assets(self) -> None:
        self.board.invalidate_piece_renderers()
        self.editor.reload_piece_assets()
        self._refresh_board()

    def start_round(self) -> None:
        self._timer.stop()
        self._attempt = []
        self._preview_index = 0
        fmt = self._current_format()
        if fmt is MemoryFormat.SHAPE:
            self._sequence_prompt = None
            self._position_target = None
            self._shape_prompt = self._shapes.generate(
                self.size_spin.value(),
                min(self.count_spin.value(), self.size_spin.value() ** 2),
                reveal_ms=self.reveal_spin.value(),
            )
            self._begin_shape_preview()
            return
        if fmt is MemoryFormat.SEQUENCE:
            self._shape_prompt = None
            self._position_target = None
            self._sequence_prompt = self._sequences.generate(
                self.size_spin.value(),
                min(self.count_spin.value(), self.size_spin.value() ** 2),
                step_ms=max(250, self.reveal_spin.value() // 4),
            )
            self._begin_sequence_preview()
            return
        self._shape_prompt = None
        self._sequence_prompt = None
        mode = self._resolve(self._mode_id)
        self._position_target = self._positions.generate(
            mode,
            piece_count=max(3, self.count_spin.value()),
            reveal_seconds=self.reveal_spin.value() / 1000,
        )
        self._begin_position_preview()

    def _current_format(self) -> MemoryFormat:
        value = self.format_combo.currentData()
        return value if isinstance(value, MemoryFormat) else MemoryFormat.SHAPE

    def _sync_controls(self) -> None:
        position = self._current_format() is MemoryFormat.POSITION
        self.size_spin.setEnabled(not position)
        self.size_spin.setPrefix("")
        if position:
            self.count_spin.setRange(3, 32)
            self.count_spin.setValue(max(6, self.count_spin.value()))
            self.hint.setText(
                "Запомните позицию, затем восстановите её в редакторе доски."
            )
        elif self._current_format() is MemoryFormat.SEQUENCE:
            self.count_spin.setRange(2, 16)
            self.hint.setText(
                "Клетки загораются по одной. Повторите тот же порядок нажатий."
            )
        else:
            self.count_spin.setRange(2, 24)
            self.hint.setText(
                "Запомните фигуру из подсвеченных клеток и нарисуйте её снова."
            )
        self._reset_idle()

    def _reset_idle(self) -> None:
        self._phase = _Phase.IDLE
        self._shape_prompt = None
        self._sequence_prompt = None
        self._position_target = None
        self._attempt = []
        self.check_button.setEnabled(False)
        self.status.setText("Нажмите «Новый раунд», чтобы начать.")
        self.status.setProperty("state", "active")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        if self._current_format() is MemoryFormat.POSITION:
            self._pages.setCurrentWidget(self.board)
            mode = self._resolve(self._mode_id)
            self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
            self.board.set_coordinates_visible(True)
            self.board.set_position({})
            self.board.clear_highlights()
        else:
            self._apply_grid_board()

    def _apply_grid_board(self) -> None:
        size = self.size_spin.value()
        self._pages.setCurrentWidget(self.board)
        self.board.set_shape(size, size)
        self.board.set_coordinates_visible(False)
        self.board.set_orientation(BoardOrientation.WHITE)
        self.board.set_position({})
        self.board.clear_highlights()

    def _begin_shape_preview(self) -> None:
        assert self._shape_prompt is not None
        self._phase = _Phase.PREVIEW
        self._apply_grid_board()
        self.board.set_highlights(lit_squares=self._shape_prompt.cells)
        self.status.setText("Запомните фигуру…")
        self.check_button.setEnabled(False)
        self._timer.start(self._shape_prompt.reveal_ms)

    def _begin_sequence_preview(self) -> None:
        assert self._sequence_prompt is not None
        self._phase = _Phase.PREVIEW
        self._apply_grid_board()
        self.status.setText("Смотрите последовательность…")
        self.check_button.setEnabled(False)
        self._preview_index = 0
        self._show_sequence_step()

    def _begin_position_preview(self) -> None:
        assert self._position_target is not None
        self._phase = _Phase.PREVIEW
        mode = self._resolve(self._mode_id)
        self._pages.setCurrentWidget(self.board)
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
        self.board.set_coordinates_visible(True)
        self.board.set_orientation(
            BoardOrientation.BLACK
            if mode.default_view_side is PieceSide.BLACK
            else BoardOrientation.WHITE
        )
        self.board.set_facing_opponent(bool(mode.facing_opponent))
        self.board.set_position(self._position_map(self._position_target))
        self.board.clear_highlights()
        self.status.setText("Запомните позицию…")
        self.check_button.setEnabled(False)
        self._timer.start(self.reveal_spin.value())

    def _show_sequence_step(self) -> None:
        prompt = self._sequence_prompt
        if prompt is None:
            return
        if self._preview_index >= len(prompt.sequence):
            self._enter_input()
            return
        square = prompt.sequence[self._preview_index]
        self.board.set_highlights(lit_squares=(square,))
        self._preview_index += 1
        self._timer.start(prompt.step_ms)

    def _on_timer(self) -> None:
        if self._phase is not _Phase.PREVIEW:
            return
        if self._sequence_prompt is not None:
            self._show_sequence_step()
            return
        self._enter_input()

    def _enter_input(self) -> None:
        self._phase = _Phase.INPUT
        self._attempt = []
        if self._current_format() is MemoryFormat.POSITION:
            self.editor.reset_empty()
            self._pages.setCurrentWidget(self.editor)
            self.status.setText("Восстановите позицию в редакторе.")
            self.check_button.setEnabled(True)
            return
        self._pages.setCurrentWidget(self.board)
        self.board.set_position({})
        self.board.clear_highlights()
        if self._current_format() is MemoryFormat.SEQUENCE:
            self.status.setText("Повторите порядок нажатий.")
            self.check_button.setEnabled(False)
        else:
            self.status.setText("Отметьте клетки фигуры, затем нажмите «Проверить».")
            self.check_button.setEnabled(True)

    def _on_square(self, index: int) -> None:
        if self._phase is not _Phase.INPUT:
            return
        if self._current_format() is MemoryFormat.SEQUENCE:
            self._attempt.append(index)
            self.board.set_highlights(selected=index, lit_squares=self._attempt[-1:])
            prompt = self._sequence_prompt
            if prompt is not None and len(self._attempt) >= len(prompt.sequence):
                self._check()
            return
        if self._current_format() is MemoryFormat.SHAPE:
            if index in self._attempt:
                self._attempt.remove(index)
            else:
                self._attempt.append(index)
            self.board.set_highlights(lit_squares=self._attempt)

    def _check(self) -> None:
        if self._phase is not _Phase.INPUT:
            return
        self._phase = _Phase.DONE
        self.check_button.setEnabled(False)
        fmt = self._current_format()
        if fmt is MemoryFormat.SHAPE and self._shape_prompt is not None:
            score = self._shapes.grade(self._shape_prompt, set(self._attempt))
            perfect = self._shapes.is_perfect(self._shape_prompt, set(self._attempt))
            self.board.set_highlights(
                lit_squares=self._attempt,
                last_move_squares=self._shape_prompt.cells,
            )
        elif fmt is MemoryFormat.SEQUENCE and self._sequence_prompt is not None:
            score = self._sequences.grade(self._sequence_prompt, self._attempt)
            perfect = self._sequences.is_perfect(self._sequence_prompt, self._attempt)
        elif fmt is MemoryFormat.POSITION and self._position_target is not None:
            diff = self._positions.compare(
                self._position_target, self.editor.current_state()
            )
            score = diff.score
            perfect = score >= 1.0
            self._pages.setCurrentWidget(self.board)
            self.board.set_shape(
                self._position_target.board_state.board.shape.files,
                self._position_target.board_state.board.shape.ranks,
            )
            self.board.set_coordinates_visible(True)
            self.board.set_position(self._position_map(self._position_target))
            self.board.set_highlights(
                error_squares=diff.extra,
                mismatch_squares=diff.mismatch,
                missed_squares=diff.missed,
            )
            self.hint.setText(
                "Показан правильный ответ. "
                "Красный — лишняя фигура, жёлтый — не та фигура, "
                "зелёный — пропущенная. Верные клетки без подсветки."
            )
        else:
            return
        if perfect:
            self.status.setText("Верно.")
            self.status.setProperty("state", "win")
        else:
            self.status.setText(f"Есть ошибки. Совпадение: {int(score * 100)}%.")
            self.status.setProperty("state", "mate")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _position_map(self, state: GameState) -> dict[int, str]:
        mode = self._resolve(self._mode_id)
        position: dict[int, str] = {}
        for index, piece in state.board_state.cells.items():
            if piece is None:
                continue
            position[index] = piece_svg_key(mode, piece)
        return position

    def _refresh_board(self) -> None:
        if self._phase is _Phase.PREVIEW and self._position_target is not None:
            self.board.set_position(self._position_map(self._position_target))
