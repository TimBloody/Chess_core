import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.training.maze import MazePuzzle, MazeSession
from chess_core.app.training.memory import MemoryFormat
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.training.maze_widget import MazeTrainingWidget
from chess_core.ui.training.memory_widget import MemoryTrainingWidget
from chess_core.ui.widgets.board_widget import BoardWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_board_widget_accepts_lit_and_blocked_highlights() -> None:
    _app()
    board = BoardWidget()
    board.set_highlights(lit_squares=(12, 28), blocked_squares=(27,))
    assert board._lit_squares == {12, 28}
    assert board._blocked_squares == {27}
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


def test_maze_widget_plays_a_fixed_rook_puzzle() -> None:
    _app()
    widget = MazeTrainingWidget()
    assert widget._session is not None
    widget._session = MazeSession.start(
        MazePuzzle(
            piece_type="rook",
            start=0,
            obstacles=frozenset({10}),
            targets={7: "pawn"},
        )
    )
    widget._refresh()
    assert widget.board.position[0] == "wR"
    assert widget.board.position[7] == "bP"
    assert widget.board.position[10] == "blocker"
    assert 7 not in widget.board._legal_destinations
    widget._on_square(8)
    assert 7 in widget.board._legal_destinations
    widget._on_square(7)
    assert widget._session.status.value == "won"
    assert "пройден" in widget.status.text().lower()
    widget.close()


def test_maze_widget_undo_and_reset() -> None:
    _app()
    widget = MazeTrainingWidget()
    widget._session = MazeSession.start(
        MazePuzzle(
            piece_type="rook",
            start=0,
            obstacles=frozenset(),
            targets={56: "pawn"},
        )
    )
    widget._refresh()
    widget._on_square(8)
    assert widget._session.hero_square == 0
    widget._on_square(56)
    assert widget._session.hero_square == 56
    widget.undo_button.click()
    assert widget._session.hero_square == 0
    widget._on_square(56)
    widget.reset_button.click()
    assert widget._session.hero_square == 0
    assert widget._session.remaining == {56: "pawn"}
    widget.close()


def test_education_maze_page_is_playable() -> None:
    _app()
    register_builtin_modes()
    from chess_core.ui.branches.education import EducationWindow

    window = EducationWindow(default_registry.list_modes(), UiSession("chess"))
    maze = window.page_widget("Лабиринт")
    assert isinstance(maze, MazeTrainingWidget)
    maze.targets_spin.setValue(1)
    maze.obstacles_spin.setValue(0)
    maze.start_round()
    assert maze._session is not None
    assert maze.board.position
    window.close()


def test_education_editor_sends_position_to_analysis() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.piece import PieceSide
    from chess_core.ui.branches.education import EducationWindow
    from chess_core.ui.editor import EditorWidget
    from chess_core.ui.pgn_analysis import PgnAnalysisWidget

    window = EducationWindow(default_registry.list_modes(), UiSession("chess"))
    editor = window.page_widget("Редактор")
    assert isinstance(editor, EditorWidget)
    assert editor.play_button.text() == "Анализировать позицию"
    editor._load_start()
    editor.play_button.click()
    analysis = window.page_widget("Анализ")
    assert isinstance(analysis, PgnAnalysisWidget)
    assert window._stack.currentWidget() is analysis
    assert not analysis._chrome_visible
    analysis.game.board.square_clicked.emit(12)
    analysis.game.board.square_clicked.emit(28)
    assert analysis.game.service.state.side_to_move is PieceSide.BLACK
    window.close()
