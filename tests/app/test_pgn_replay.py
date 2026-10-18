"""PGN import and replay onto LocalGameService."""

from chess_core.app.game import LocalGameService
from chess_core.app.pgn_replay import looks_like_pgn, move_tokens_from_movetext
from chess_core.modes import resolve_mode

_CLASSIC = """[Event "Chess Core"]
[Site "Local"]
[Date "2026.08.31"]
[Mode "classic_chess"]
[Result "1-0"]

1. e4  e5
2. Qh5  Nc6

1-0
"""

_MULTI = """[Event "A"]
[White "One"]
[Black "Two"]
[Result "1/2-1/2"]

1. e4 e5 1/2-1/2

[Event "B"]
[White "Three"]
[Black "Four"]
[Result "1-0"]

1. d4 d5 2. c4 1-0
"""


def test_looks_like_pgn() -> None:
    assert looks_like_pgn(_CLASSIC)
    assert not looks_like_pgn("hello world")


def test_move_tokens_skip_numbers_and_results() -> None:
    tokens = move_tokens_from_movetext("1. e4 e5 2. Nf3 1-0")
    assert tokens == ("e4", "e5", "Nf3")


def test_move_tokens_keep_mainline_when_variation_is_present() -> None:
    tokens = move_tokens_from_movetext("1. e4 e5 (1... c5 2. Nf3) 2. Nf3")
    assert tokens == ("e4", "e5", "Nf3")


def test_import_pgn_replays_mainline() -> None:
    service = LocalGameService(resolve_mode("chess"), allow_temporary_variations=True)
    service.import_pgn(_CLASSIC)
    assert service.record.live_revision == 4
    assert [line.text for line in service.move_log_lines] == ["1. e4  e5", "2. Qh5  Nc6"]


def test_import_pgn_game_index() -> None:
    service = LocalGameService(resolve_mode("chess"), allow_temporary_variations=True)
    service.import_pgn(_MULTI, game_index=1)
    assert service.record.live_revision == 3
    assert "c4" in service.move_log_lines[-1].text or "c4" in service.move_log_lines[1].text


def test_variation_from_archive_position() -> None:
    service = LocalGameService(resolve_mode("chess"), allow_temporary_variations=True)
    service.import_pgn(_CLASSIC)
    service.go_to_revision(2)
    assert not service.is_live
    service.play(service.legal_moves()[0])
    assert service.in_variation
    assert service.record.live_revision == 3
    service.return_to_mainline()
    assert not service.in_variation
    assert service.record.live_revision == 4
