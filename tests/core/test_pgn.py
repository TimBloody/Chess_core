"""PGN parse/format for ChessBase 16 databases."""

from chess_core.core.pgn import (
    SEVEN_TAG_ROSTER,
    format_pgn_database,
    format_pgn_game,
    merge_pgn_games,
    parse_pgn,
)


_CLASSIC_TRANSCRIPT = """[Event "Chess Core"]
[Site "Local"]
[Date "2026.08.31"]
[Mode "classic_chess"]
[ModeName "Классика"]
[Result "1-0"]
[PlyCount "4"]
[Termination "мат"]

1. e4  e5
2. Qh5  Nc6

1-0
мат
"""


_STANDARD_PGN = """[Event "Test"]
[Site "Berlin"]
[Date "2026.01.02"]
[Round "1"]
[White "Анна"]
[Black "Борис"]
[Result "1/2-1/2"]

1. e4 e5 2. Nf3 Nc6 {спокойная игра} 1/2-1/2
"""


def test_parse_chess_core_transcript_fills_seven_tag_roster() -> None:
    games = parse_pgn(_CLASSIC_TRANSCRIPT)
    assert len(games) == 1
    game = games[0]
    formatted = format_pgn_game(game)
    for name in SEVEN_TAG_ROSTER:
        assert f"[{name} " in formatted
    assert '[White "?"]' in formatted
    assert '[Black "?"]' in formatted
    assert '[Round "-"]' in formatted
    assert formatted.strip().endswith("1-0")
    assert "{мат}" in formatted
    assert not formatted.strip().endswith("мат")
    assert formatted.count("1-0") == 2  # tag + movetext


def test_parse_standard_pgn_keeps_cyrillic_names_and_result() -> None:
    games = parse_pgn(_STANDARD_PGN)
    assert len(games) == 1
    assert games[0].white == "Анна"
    assert games[0].black == "Борис"
    assert games[0].result == "1/2-1/2"
    assert "спокойная игра" in games[0].comment or "спокойная игра" in games[0].moves


def test_multi_game_database_round_trip() -> None:
    text = format_pgn_database(parse_pgn(_STANDARD_PGN + "\n\n" + _CLASSIC_TRANSCRIPT))
    games = parse_pgn(text)
    assert len(games) == 2
    assert games[0].white == "Анна"
    assert games[1].result == "1-0"
    assert text.endswith("\n")
    assert "\n\n[Event " in text


def test_merge_skips_duplicate_identity() -> None:
    first = parse_pgn(_CLASSIC_TRANSCRIPT)
    merged = merge_pgn_games(first, first)
    assert len(merged) == 1
    extra = parse_pgn(_STANDARD_PGN)
    merged = merge_pgn_games(first, extra)
    assert len(merged) == 2
