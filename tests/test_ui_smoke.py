import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from play_classic import ClassicGameWindow
from chess_core.app.game import GameStatus
from chess_core.core.notation import to_fen
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.tools.classical_demo import parse_move
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.widgets.board_widget import (
    BoardNotation,
    BoardOrientation,
    BoardWidget,
)

_APP: QApplication | None = None


def _square_center(board: BoardWidget, square: int) -> QPointF:
    board_rect, cell_size = board._board_geometry()
    display = board.logical_to_display_square(square)
    file = display % board.files
    rank = display // board.files
    return QPointF(
        board_rect.left() + (file + 0.5) * cell_size,
        board_rect.top() + (board.ranks - rank - 0.5) * cell_size,
    )

def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_assets_and_rectangular_board_widget_contract() -> None:
    _app()
    assets = AssetsLoader()
    assert assets.piece_path("wK").is_file()
    assert assets.piece_path("0FU").is_file()
    board = BoardWidget(assets_loader=assets)
    board.set_shape(5, 4)
    board.resize(500, 400)
    board.set_position({0: "wK", 19: "bK"})
    assert (board.files, board.ranks, board.position) == (5, 4, {0: "wK", 19: "bK"})
    assert board.square_at_position(QPointF(50, 350)) == 0
    assert board.square_at_position(QPointF(450, 50)) == 19
    assert not board.is_light_square(0)  # a1/lower-left is dark
    assert board.is_light_square(1)

    board.set_orientation(BoardOrientation.BLACK)
    assert board.logical_to_display_square(0) == 19
    assert board.display_to_logical_square(19) == 0
    assert board.logical_to_display_square(19) == 0
    assert board.display_to_logical_square(0) == 19
    assert board.square_at_position(QPointF(50, 350)) == 19
    assert board.square_at_position(QPointF(450, 50)) == 0


def test_board_color_and_piece_corner_contract_in_both_orientations() -> None:
    _app()
    board = BoardWidget()
    board.resize(640, 640)
    board.set_position({0: "wR"})

    assert board.display_to_logical_square(0) == 0
    assert not board.is_light_square(board.display_to_logical_square(0))
    assert board.logical_to_display_square(0) == 0

    board.flip_orientation()
    assert board.orientation is BoardOrientation.BLACK
    assert board.display_to_logical_square(0) == 63  # h8 is lower-left
    assert not board.is_light_square(board.display_to_logical_square(0))
    assert board.logical_to_display_square(0) == 63  # a1 moved to opposite corner
    assert board.position == {0: "wR"}  # position cache remains logical


def test_notation_order_and_generated_files_in_both_orientations() -> None:
    _app()
    board = BoardWidget()

    assert board.edge_labels() == (
        ("a", "b", "c", "d", "e", "f", "g", "h"),
        ("1", "2", "3", "4", "5", "6", "7", "8"),
    )
    board.flip_orientation()
    assert board.edge_labels() == (
        ("h", "g", "f", "e", "d", "c", "b", "a"),
        ("8", "7", "6", "5", "4", "3", "2", "1"),
    )

    board.set_shape(28, 3)
    assert BoardNotation.default_file_labels(28)[-3:] == ["z", "aa", "ab"]
    assert board.edge_labels()[0][:3] == ("ab", "aa", "z")
    assert board.edge_labels()[1] == ("3", "2", "1")


def test_notation_uses_upright_text_and_layout_survives_resize() -> None:
    _app()
    board = BoardWidget()
    board.set_shape(10, 6)
    board.resize(173, 119)
    board_rect, cell_size = board._board_geometry()
    assert board_rect.left() >= 0
    assert board_rect.top() >= 0
    assert board_rect.right() <= board.width()
    assert board_rect.bottom() < board.height()  # bottom notation has reserved space
    assert cell_size > 0

    image = QImage(board.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    transform_before = painter.worldTransform()
    board._draw_coordinates(painter, board_rect, cell_size)
    assert painter.worldTransform() == transform_before
    assert painter.worldTransform().isIdentity()
    painter.end()

    for orientation in (BoardOrientation.WHITE, BoardOrientation.BLACK):
        board.set_orientation(orientation)
        board_rect, cell_size = board._board_geometry()
        for display_rank in range(board.ranks):
            for display_file in range(board.files):
                center = QPointF(
                    board_rect.left() + (display_file + 0.5) * cell_size,
                    board_rect.top()
                    + (board.ranks - display_rank - 0.5) * cell_size,
                )
                expected = board.transform.display_index_to_logical(
                    display_rank * board.files + display_file
                )
                assert board.square_at_position(center) == expected


def test_local_play_window_contains_working_local_game_page() -> None:
    _app()
    register_builtin_modes()
    from chess_core.ui.branches.local_play import LocalPlayWindow

    window = LocalPlayWindow(default_registry.list_modes(), UiSession("chess"))
    assert isinstance(window._local_game, LocalGameWidget)
    assert window._local_game.board.position[4] == "wK"
    assert window._editor.play_button.text() == "Играть с позиции"
    window._local_game.set_mode("cylindrical")
    assert window._local_game.board.files == 8
    window.close()


def test_education_window_contains_puzzles_and_memory() -> None:
    _app()
    register_builtin_modes()
    from chess_core.ui.branches.education import EducationWindow
    from chess_core.ui.puzzles import PuzzleWidget
    from chess_core.ui.pgn_analysis import PgnAnalysisWidget
    from chess_core.ui.editor import EditorWidget
    from chess_core.ui.training.memory_widget import MemoryTrainingWidget
    from chess_core.ui.training.maze_widget import MazeTrainingWidget

    window = EducationWindow(default_registry.list_modes(), UiSession("chess"))
    assert isinstance(window._puzzles, PuzzleWidget)
    assert window._puzzles.theme_combo.count() > 1
    assert window._puzzles.session.total >= 20
    assert isinstance(window._memory, MemoryTrainingWidget)
    assert isinstance(window.page_widget("Редактор"), EditorWidget)
    assert window.page_widget("Редактор").play_button.text() == "Анализировать позицию"
    assert isinstance(window.page_widget("Анализ"), PgnAnalysisWidget)
    assert isinstance(window.page_widget("Лабиринт"), MazeTrainingWidget)
    assert window._puzzles.board.files == 8
    window.close()


def test_window_width_is_not_forced_by_unwrapped_hint_text() -> None:
    app = _app()
    register_builtin_modes()
    from chess_core.ui.branches.local_play import LocalPlayWindow

    window = LocalPlayWindow(default_registry.list_modes(), UiSession("chess"))
    window.show()
    app.processEvents()
    assert window.minimumSizeHint().width() < 1400
    assert window.width() <= 1400
    window._local_game.set_mode("gobblet")
    app.processEvents()
    assert window.minimumSizeHint().width() < 1400
    window._local_game.set_mode("shogi")
    app.processEvents()
    assert window.minimumSizeHint().width() < 1400
    window.close()


def test_classic_launcher_window_performs_a_legal_move_offscreen() -> None:
    _app()
    window = ClassicGameWindow()

    assert len(window.game.board.position) == 32
    assert window.game.board.position[12] == "wP"  # e2
    window.game.board.square_clicked.emit(12)
    window.game.board.square_clicked.emit(36)  # e5 is illegal from e2
    assert window.game.board.position[12] == "wP"
    assert window.game.service.state.side_to_move is PieceSide.WHITE
    window.game.board.square_clicked.emit(12)
    window.game.board.square_clicked.emit(28)  # e4

    assert 12 not in window.game.board.position
    assert window.game.board.position[28] == "wP"
    assert window.game.service.state.side_to_move is PieceSide.BLACK
    window.game.reset_game()
    assert window.game.board.position[12] == "wP"
    window.close()


def test_flip_shortcut_preserves_state_cache_and_flipped_click_mapping() -> None:
    app = _app()
    window = ClassicGameWindow()
    window.show()
    app.processEvents()
    game = window.game
    game.board.resize(640, 640)
    game.board.square_clicked.emit(12)  # cache e2 pawn moves
    state_before = game.service.state
    moves_before = game.service.selected_moves
    side_before = game.service.state.side_to_move

    QTest.keyClick(window, Qt.Key.Key_F)
    app.processEvents()

    assert game.board.orientation is BoardOrientation.BLACK
    assert game.board.edge_labels() == (
        ("h", "g", "f", "e", "d", "c", "b", "a"),
        ("8", "7", "6", "5", "4", "3", "2", "1"),
    )
    assert game.service.state.side_to_move is side_before
    assert game.service.selected_moves == moves_before

    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier)
    app.processEvents()
    assert game.board.orientation is BoardOrientation.WHITE
    assert game.service.state.side_to_move is side_before
    assert game.service.selected_moves == moves_before
    QTest.keyClick(window, Qt.Key.Key_F)
    app.processEvents()

    e2 = _square_center(game.board, 12)
    e4 = _square_center(game.board, 28)
    assert game.board.square_at_position(e2) == 12
    assert game.board.square_at_position(e4) == 28

    game.board.square_clicked.emit(game.board.square_at_position(e4))
    assert game.board.position[28] == "wP"
    assert game.service.state.side_to_move is PieceSide.BLACK
    window.close()


def test_r_shortcut_resets_only_after_terminal_status() -> None:
    app = _app()
    window = ClassicGameWindow()
    window.show()
    app.processEvents()
    game = window.game
    game.service.play(parse_move("e2e4"))
    active_fen = to_fen(game.service.state)

    QTest.keyClick(window, Qt.Key.Key_R)
    app.processEvents()

    assert to_fen(game.service.state) == active_fen
    assert "не сбрасывает" in game.status.text()

    game.reset_game()
    for value in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        game.service.play(parse_move(value))
    assert game.service.status() is GameStatus.CHECKMATE

    QTest.keyClick(window, Qt.Key.Key_R)
    app.processEvents()

    assert game.service.status() is GameStatus.ACTIVE
    assert len(game.board.position) == 32
    assert game.service.state.side_to_move is PieceSide.WHITE
    window.close()
