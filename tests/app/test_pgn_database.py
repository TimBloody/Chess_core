"""PGN database service: collect, create, append."""

from chess_core.app.pgn_database import PgnDatabaseService
from chess_core.core.pgn import parse_pgn


def test_collect_old_transcript_and_pgn_into_one_database() -> None:
    service = PgnDatabaseService()
    transcript = """[Event "Chess Core"]
[Site "Local"]
[Date "2026.08.30"]
[Mode "classic_chess"]
[Result "0-1"]

1. e4 e5
2. Qh5 Nc6

0-1
мат
"""
    pgn = """[Event "Club"]
[Site "Moscow"]
[Date "2026.08.31"]
[Round "2"]
[White "Иванов"]
[Black "Петров"]
[Result "1-0"]

1. d4 d5 1-0
"""
    games = service.collect_from_texts(
        (("a.txt", transcript), ("b.pgn", pgn)),
    )
    text = service.create_database(games)
    parsed = parse_pgn(text)
    assert len(parsed) == 2
    assert parsed[0].result == "0-1"
    assert parsed[1].white == "Иванов"
    assert "[Round " in text
    assert "[White " in text
    assert "[Black " in text


def test_append_adds_only_new_games() -> None:
    service = PgnDatabaseService()
    existing = service.create_database(
        service.parse_text(
            """[Event "A"]
[Site "?"]
[Date "2026.01.01"]
[Round "-"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""
        )
    )
    extra = service.parse_text(
        """[Event "A"]
[Site "?"]
[Date "2026.01.01"]
[Round "-"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""
    )
    same = service.append_to_database(existing, extra)
    assert service.added_count(existing, same) == 0
    other = service.parse_text(
        """[Event "B"]
[Site "?"]
[Date "2026.01.02"]
[Round "-"]
[White "C"]
[Black "D"]
[Result "0-1"]

1. d4 d5 0-1
"""
    )
    appended = service.append_to_database(existing, other)
    assert service.added_count(existing, appended) == 1
    assert len(parse_pgn(appended)) == 2
