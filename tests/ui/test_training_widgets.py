import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.training.memory import MemoryFormat
from chess_core.app.training.maze import MazePuzzle, MazeSession
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.training.hub import TrainingHubWidget
from chess_core.ui.training.memory_widget import MemoryTrainingWidget
from chess_core.ui.widgets.board_widget import BoardWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_board_widget_accepts_lit_and_dot_highlights() -> None:
    _app()
    board = BoardWidget()
    board.set_highlights(lit_squares=(12, 28), dot_squares=(27,))
    assert board._lit_squares == {12, 28}
    assert board._dot_squares == {27}
    board.close()


def test_position_memory_review_shows_answer_and_error_colors() -> None:
    _app()
    register_builtin_modes()
    widget = MemoryTrainingWidget()
    index = widget.format_combo.findData(MemoryFormat.POSITION)
    widget.format_combo.setCurrentIndex(index)
    widget.count_spin.setValue(4)
    widget.reveal_spin.setValue(1)
    widget.start_round()
    widget._timer.stop()
    widget._enter_input()
    target = widget._position_target
    assert target is not None
    empty = next(
        square
        for square in range(target.board_state.board.shape.cell_count)
        if target.board_state.cells.get(square) is None
    )
    occupied = next(
        square
        for square, piece in target.board_state.cells.items()
        if piece is not None
    )
    widget.editor._service.set_piece(empty, "pawn", "white")
    widget._check()
    assert widget._pages.currentWidget() is widget.board
    assert empty in widget.board._error_squares
    assert occupied in widget.board._missed_squares
    assert occupied not in widget.board._error_squares
    assert occupied in widget.board.position
    assert "правильный ответ" in widget.hint.text().lower()
    widget.close()


def test_training_hub_starts_shape_round_and_maze_session() -> None:
    _app()
    register_builtin_modes()
    hub = TrainingHubWidget(default_registry.get, "chess")
    hub.memory.size_spin.setValue(3)
    hub.memory.count_spin.setValue(3)
    hub.memory.reveal_spin.setValue(1)
    hub.memory.start_round()
    assert hub.memory._shape_prompt is not None
    hub.memory._timer.stop()
    hub.memory._enter_input()
    first = next(iter(hub.memory._shape_prompt.cells))
    hub.memory._on_square(first)
    assert first in hub.memory._attempt

    hub.maze_button.click()
    hub.maze._session = MazeSession.start(
        MazePuzzle(
            piece_type="rook",
            start=0,
            obstacles=frozenset({10}),
            targets={7: "pawn"},
        )
    )
    hub.maze._refresh()
    assert hub.maze.board.position[0] == "wR"
    assert 10 in hub.maze.board._dot_squares
    hub.close()


def test_main_window_has_education_page() -> None:
    _app()
    register_builtin_modes()
    window = MainWindow(default_registry.list_modes(), UiSession("chess"))
    assert "Обучение" in window._nav_buttons
    assert "По памяти" not in window._nav_buttons
    assert window._training is not None
    window._nav_buttons["Обучение"].click()
    assert window._stack.currentWidget() is window._training
    window.close()
