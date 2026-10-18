import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from chess_core.app.game import LocalGameService
from chess_core.app.pgn_replay import resolve_turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import PieceSide
from chess_core.modes import register_builtin_modes, resolve_mode
from chess_core.ui.pgn_analysis import PgnAnalysisWidget

_APP: QApplication | None = None

_CLASSIC = """[Event "Chess Core"]
[Site "Local"]
[Date "2026.08.31"]
[Mode "classic_chess"]
[Result "1-0"]

1. e4  e5
2. Qh5  Nc6

1-0
"""

_MULTI = """[Event "ДФО2025_Д11"]
[Site "?"]
[Date "2025.11.13"]
[Round "9.112"]
[White "Еланова, Марина"]
[Black "Ертуханова, София"]
[Result "1/2-1/2"]
[ECO "D02"]

1. Nf3 Nf6 2. d4 d5 1/2-1/2

[Event "ДФО2025_Д11"]
[Site "?"]
[Date "2025.11.13"]
[Round "9.113"]
[White "Макарова, Анастасия"]
[Black "Еланова, Марина"]
[Result "1-0"]
[ECO "B23"]

1. e4 c5 2. f4 e6 1-0
"""

_SEARCH = """[Event "A"]
[White "Alpha"]
[Black "Beta"]
[Result "*"]

1. Nf3 Nf6 2. d4 d5 3. c4 *

[Event "B"]
[White "Gamma"]
[Black "Delta"]
[Result "*"]

1. d4 d5 2. Nf3 Nf6 3. e3 *

[Event "C"]
[White "Epsilon"]
[Black "Zeta"]
[Result "*"]

1. e4 e5 *
"""


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_pgn_analysis_loads_from_text_and_file(tmp_path: Path) -> None:
    _app()
    register_builtin_modes()
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    assert widget.load_pgn(_CLASSIC)
    assert widget.game.service.record.live_revision == 4

    pgn_file = tmp_path / "game.pgn"
    pgn_file.write_text(_CLASSIC, encoding="utf-8")
    widget.pgn_text.setPlainText(pgn_file.read_text(encoding="utf-8"))
    assert widget.load_pgn()
    widget.close()


def test_pgn_analysis_export_buttons_enabled_after_load() -> None:
    _app()
    register_builtin_modes()
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    widget.load_pgn(_CLASSIC)
    assert widget.game.copy_record_button.isEnabled()
    assert widget.game.save_record_button.isEnabled()
    assert widget.game.add_to_database_button.isEnabled()
    widget.close()


def test_pgn_analysis_multi_game_list_and_navigation() -> None:
    _app()
    register_builtin_modes()
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    assert widget.load_pgn(_MULTI)
    assert len(widget.games) == 2
    assert widget.games_table.rowCount() == 2
    assert widget.current_index == 0
    assert widget.games_table.item(0, 1).text() == "Еланова, Марина"
    assert widget.games_table.item(1, 1).text() == "Макарова, Анастасия"
    assert widget.next_button.isEnabled()
    assert not widget.prev_button.isEnabled()

    assert widget.open_next_game()
    assert widget.current_index == 1
    assert widget.game.service.record.live_revision == 4
    assert widget.prev_button.isEnabled()
    assert not widget.next_button.isEnabled()

    assert widget.open_game_at(0)
    assert widget.current_index == 0
    widget.close()


def test_pgn_analysis_chrome_toggle_and_board_click() -> None:
    _app()
    register_builtin_modes()
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    assert widget._chrome_visible
    widget.toggle_chrome()
    assert not widget._chrome_visible
    assert widget._chrome.isHidden()
    widget.toggle_chrome()
    assert widget._chrome_visible
    assert not widget._chrome.isHidden()

    widget.game.board.square_clicked.emit(12)
    assert not widget._chrome_visible
    widget.close()


def test_pgn_analysis_loads_editor_position_and_allows_moves() -> None:
    _app()
    register_builtin_modes()
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    start = resolve_mode("chess").initial_state()
    widget.load_position(start)
    assert not widget._chrome_visible
    assert widget.game.service.record.live_revision == 0
    widget.game.board.square_clicked.emit(12)
    widget.game.board.square_clicked.emit(28)
    assert widget.game.service.state.side_to_move is PieceSide.BLACK
    widget.close()


def test_position_search_filters_transpositions_and_jumps_to_the_ply() -> None:
    _app()
    register_builtin_modes()
    mode = resolve_mode("chess")
    widget = PgnAnalysisWidget(resolve_mode, "chess")
    assert widget.load_pgn(_SEARCH)
    assert widget.games_table.rowCount() == 3
    assert widget.search_position_button.isEnabled()

    service = LocalGameService(mode)
    generator = MoveGenerator(mode)
    for san in ("d4", "d5", "Nf3", "Nf6"):
        service.play_turn(resolve_turn(service.state, san, generator))

    assert widget.search_position(service.state) == 2
    assert widget.games_table.rowCount() == 2
    assert widget.games_table.item(0, 1).text() == "Alpha"
    assert widget.games_table.item(1, 1).text() == "Gamma"
    assert widget.current_index == 0
    assert widget.game.service.record.view_revision == 4
    assert widget.game.service.state.side_to_move is PieceSide.WHITE
    assert widget._chrome_visible

    assert widget.open_next_game()
    assert widget.current_index == 1
    assert widget.game.service.record.view_revision == 4
    assert not widget.open_next_game()

    widget.clear_position_filter()
    assert widget.games_table.rowCount() == 3
    assert not widget.show_all_button.isEnabled()
    widget.close()
