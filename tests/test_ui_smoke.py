import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from play_classic import ClassicGameWindow
from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.notation import to_fen
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.infra.pgn_storage import PgnMetadata, PgnStorage
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess
from chess_core.tools.classical_demo import parse_move
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.pgn_viewer import PgnViewerWidget
from chess_core.ui.widgets.board_widget import (
    BoardNotation,
    BoardOrientation,
    BoardWidget,
)

_APP: QApplication | None = None

def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_assets_and_rectangular_board_widget_contract() -> None:
    _app()
    assets = AssetsLoader()
    assert assets.piece_path("wK").is_file()
    assert assets.piece_path("0FU").is_file()
    assert "kanji_brown" in str(assets.piece_path("0FU")).replace("\\", "/")
    assert assets.piece_path("0OU@w").is_file()
    assert assets.piece_path("dobutsu/0FU@b").is_file()
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


def test_stylized_shogi_set_is_optional() -> None:
    from chess_core.ui.assets_loader import DEFAULT_SHOGI_SET, set_shogi_piece_set, shogi_piece_set

    assets = AssetsLoader()
    try:
        set_shogi_piece_set("shogi_bnw")
        path = str(assets.piece_path("0FU")).replace("\\", "/")
        assert "shogi_bnw" in path
    finally:
        set_shogi_piece_set(DEFAULT_SHOGI_SET)
    assert shogi_piece_set() == DEFAULT_SHOGI_SET


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


def test_main_window_contains_working_local_game_page() -> None:
    _app()
    register_builtin_modes()
    window = MainWindow(default_registry.list_modes(), UiSession("chess"))
    assert isinstance(window._local_game, LocalGameWidget)
    assert isinstance(window._pgn_viewer, PgnViewerWidget)
    assert window._local_game.board.position[4] == "wK"
    window._local_game.set_mode("cylindrical")
    assert window._local_game.board.files == 8
    window._local_game.set_mode("shogi")
    assert window._local_game.board.files == 9
    assert window._local_game.board.orientation is BoardOrientation.BLACK
    assert window._local_game.board.position[76] == "0OU@b"
    assert window._local_game.board.position[4] == "0OU@w"
    assert window._local_game.black_pocket.is_grid
    assert not window._local_game._hand_rail.isHidden()
    window._local_game.set_mode("crazyhouse")
    assert not window._local_game.black_pocket.is_grid
    assert not window._local_game._top_bar.isHidden()
    window._local_game.set_mode("dobutsu_shogi")
    assert window._local_game.board.files == 3
    assert window._local_game.board.position[10] == "dobutsu/0OU@b"
    sidebar = window._local_game._main_split.widget(1)
    assert sidebar.minimumWidth() >= 380
    assert window._local_game.black_clock._time.font().pixelSize() >= 28
    window.close()


def test_pgn_viewer_loads_pasted_game() -> None:
    app = _app()
    mode = classic_chess()
    source = LocalGameService(mode)
    source.play(parse_move("e2e4"))
    source.play(parse_move("e7e5"))
    viewer = PgnViewerWidget(lambda _mode_id: mode, mode.id)
    viewer.pgn_text.setPlainText(source.export_pgn())

    assert viewer.load_pgn()
    assert viewer.game.service.record.live_revision == 2
    assert viewer.game._clock_service is None
    assert not viewer.game._ui_timer.isActive()
    assert viewer.game._clock_rail.isHidden()
    assert viewer.game.clock_mode.isHidden()
    assert viewer.game.move_list.count() == 2
    assert viewer.game.move_list.item(0).data(256) == 0
    assert viewer.game.move_list.item(1).data(256) == 2
    assert viewer.game.move_list.item(1).text() == "1. e4 e5"
    assert viewer.game.board.position[28] == "wP"
    viewer.game.move_list._on_item_clicked(viewer.game.move_list.item(0))
    assert viewer.game.service.record.view_revision == 0

    viewer.show()
    viewer.game.setFocus()
    app.processEvents()
    QTest.keyClick(viewer.game, Qt.Key.Key_Right)
    app.processEvents()
    assert viewer.game.service.record.view_revision == 1
    assert 36 not in viewer.game.board.position
    QTest.keyClick(viewer.game, Qt.Key.Key_Right)
    assert viewer.game.service.record.view_revision == 2
    QTest.keyClick(viewer.game, Qt.Key.Key_Left)
    assert viewer.game.service.record.view_revision == 1
    assert viewer.game.service.can_play
    viewer.close()


def test_local_game_saves_chessbase_compatible_pgn(tmp_path: Path) -> None:
    _app()
    mode = classic_chess()
    game = LocalGameWidget(lambda _mode_id: mode, mode.id)
    target = game.save_pgn(
        PgnMetadata(event="Analysis", white="Alice", annotator="Coach"),
        "lesson.pgn",
        storage=PgnStorage(tmp_path),
    )
    text = target.read_text(encoding="utf-8")
    assert target.name == "lesson.pgn"
    assert '[Event "Analysis"]' in text
    assert '[Annotator "Coach"]' in text
    assert game.save_pgn_button.text() == "Сохранить PGN"
    game.close()


def test_clock_stays_idle_until_first_completed_turn() -> None:
    _app()
    mode = classic_chess()
    game = LocalGameWidget(lambda _mode_id: mode, mode.id)
    assert game._clock_service is not None
    idle = game._clock_service.snapshot()
    assert not game._clock_service.has_started
    assert idle.running_side is None
    game.board.square_clicked.emit(12)
    game.board.square_clicked.emit(28)
    started = game._clock_service.snapshot()
    assert game._clock_service.has_started
    assert started.running_side is PieceSide.BLACK
    game.reset_game()
    assert not game._clock_service.has_started
    assert game._clock_service.snapshot().running_side is None
    game.close()


def test_history_view_pauses_and_hides_clock_until_live() -> None:
    _app()
    mode = classic_chess()
    game = LocalGameWidget(lambda _mode_id: mode, mode.id)
    game.service.play(parse_move("e2e4"))
    game._refresh()

    game._on_revision_selected(0)
    assert game._clock_service is not None
    assert game._clock_service.is_paused
    assert game._clock_rail.isHidden()
    assert game.clock_mode.isHidden()

    game._go_live()
    assert not game._clock_service.is_paused
    assert not game._clock_rail.isHidden()
    assert not game.clock_mode.isHidden()
    game.close()


def _square_center(board: BoardWidget, square: int) -> QPointF:
    board_rect, cell_size = board._board_geometry()
    return board._logical_square_rect(board_rect, cell_size, square).center()


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

    assert game.board.square_at_position(_square_center(game.board, 12)) == 12  # e2
    assert game.board.square_at_position(_square_center(game.board, 28)) == 28  # e4

    game.board.square_clicked.emit(game.board.square_at_position(_square_center(game.board, 28)))
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


def test_mate_pauses_clock_and_offers_pgn_save_once(monkeypatch) -> None:
    _app()
    window = ClassicGameWindow()
    game = window.game
    prompted: list[bool] = []
    monkeypatch.setattr(game, "_prompt_save_pgn", lambda: prompted.append(True))

    for value in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        game.service.play(parse_move(value))
    game._refresh()

    assert game.service.status() is GameStatus.CHECKMATE
    assert game._clock_service is not None
    assert game._clock_service.is_paused
    assert game._clock_service.snapshot().running_side is None
    frozen = game._clock_service.snapshot().black_remaining_ms

    game._maybe_prompt_pgn_save()
    game._maybe_prompt_pgn_save()
    assert prompted == [True]
    assert game._suggested_result() == "1-0"
    assert game._clock_service.snapshot().black_remaining_ms == frozen
    window.close()
