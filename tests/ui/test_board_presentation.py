import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from chess_core.app.engine import BestMove, EngineEvaluation, EngineHintService
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess, king_of_the_hill, two_move_chess
from chess_core.tools.classical_demo import parse_move
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.theme import app_icon, mode_display_name
from chess_core.ui.widgets.board_widget import BoardWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_mode_display_name_for_presets_and_composed_ids() -> None:
    assert mode_display_name("chess") == "Классика"
    assert mode_display_name("three_check") == "Три шаха"
    assert "Fairytale" in mode_display_name("chess+fairytale+three_check")
    assert "Три шаха" in mode_display_name("chess+fairytale+three_check")


def test_app_icon_renders_from_packaged_knight() -> None:
    _app()
    icon = app_icon()
    assert not icon.isNull()


def test_board_last_move_and_capture_markers_are_presentation_only() -> None:
    _app()
    board = BoardWidget()
    board.set_position({4: "wK", 60: "bK", 27: "bP"})
    board.set_highlights(
        selected=12,
        legal_destinations=(20, 27),
        last_move_squares=(12, 28),
        hint_squares=(27, 28, 35, 36),
        engine_squares=(12, 28),
    )
    assert board._last_move_squares == {12, 28}
    assert board._hint_squares == {27, 28, 35, 36}
    assert board._engine_squares == {12, 28}
    assert 27 in board._legal_destinations


def test_local_game_highlights_last_move_after_e4() -> None:
    _app()
    game = LocalGameWidget(lambda _mode_id: classic_chess(), "chess")
    game.service.play(parse_move("e2e4"))
    game._refresh()
    assert game.board._last_move_squares == {12, 28}
    game.close()


def test_two_move_shows_pending_piece_and_allows_second_move_of_same_piece() -> None:
    _app()
    game = LocalGameWidget(lambda _mode_id: two_move_chess(), "two_move")
    game.service.play(parse_move("e2e4"))
    game.service.play(parse_move("b8c6"))
    game._refresh()
    c6, b8, a5 = 42, 57, 32
    assert game.board.position.get(c6) == "bN"
    assert b8 not in game.board.position
    assert "второй ход" in game.status.text()
    game.board.square_clicked.emit(c6)
    assert a5 in game.board._legal_destinations
    game.board.square_clicked.emit(a5)
    assert game.service.state.side_to_move is PieceSide.WHITE
    assert game.board.position.get(a5) == "bN"
    game.close()


def test_koth_hints_mark_the_four_centre_squares() -> None:
    _app()
    game = LocalGameWidget(lambda _mode_id: king_of_the_hill(), "king_of_the_hill")
    game._refresh()
    assert game.board._hint_squares == {27, 28, 35, 36}
    game.close()


def test_engine_hint_paints_purple_move_and_eval_bar() -> None:
    _app()
    game = LocalGameWidget(
        lambda _mode_id: classic_chess(),
        "chess",
        hint_service=EngineHintService(engines=()),
    )
    game._apply_engine_hint(
        BestMove(
            "e2e4",
            EngineEvaluation(score_cp=35, mate_in=None, pv=("e2e4",), depth=12),
        )
    )
    assert game.board._engine_squares == {12, 28}
    assert "+0.3" in game.evaluation_bar._bar.text()
    game.service.play(parse_move("e2e4"))
    game._clear_engine_hint()
    game._refresh()
    assert game.board._engine_squares == set()
    game.close()


def test_hint_button_exists_on_local_game() -> None:
    _app()
    game = LocalGameWidget(
        lambda _mode_id: classic_chess(),
        "chess",
        hint_service=EngineHintService(engines=()),
    )
    assert game.hint_button.text() == "Подсказка"
    game.close()


def test_main_window_marks_local_game_nav_button() -> None:
    _app()
    register_builtin_modes()
    window = MainWindow(default_registry.list_modes(), UiSession("chess"))
    local = window._nav_buttons["Локальная игра"]
    assert local.isChecked()
    window.close()


def test_board_hover_clears_on_leave() -> None:
    _app()
    board = BoardWidget()
    board._hover_square = 12
    board.leaveEvent(QEvent(QEvent.Type.Leave))
    assert board._hover_square is None
    board.close()
