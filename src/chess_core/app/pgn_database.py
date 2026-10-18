"""Build and extend PGN databases from saved games and transcripts."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from chess_core.core.pgn import (
    PgnGame,
    format_pgn_database,
    merge_pgn_games,
    normalize_pgn_game,
    parse_pgn,
)


@dataclass(frozen=True, slots=True)
class SourcedPgnGame:
    game: PgnGame
    source: str = ""


class PgnDatabaseService:
    """Collect games from text, merge them, and emit a ChessBase PGN database."""

    def parse_text(self, text: str, *, source: str = "") -> tuple[SourcedPgnGame, ...]:
        games = parse_pgn(text)
        if games:
            return tuple(
                SourcedPgnGame(game=normalize_pgn_game(game), source=source) for game in games
            )
        stripped = text.strip()
        if not stripped:
            return ()
        fallback = normalize_pgn_game(
            PgnGame(
                tags=(
                    ("Event", Path(source).stem or "Chess Core"),
                    ("Site", "?"),
                    ("Date", "????.??.??"),
                    ("Round", "-"),
                    ("White", "?"),
                    ("Black", "?"),
                    ("Result", "*"),
                ),
                moves=stripped,
            )
        )
        return (SourcedPgnGame(game=fallback, source=source),)

    def collect_from_texts(
        self,
        items: Iterable[tuple[str, str]],
        *,
        skip_duplicates: bool = True,
    ) -> tuple[SourcedPgnGame, ...]:
        collected: list[SourcedPgnGame] = []
        seen: set[tuple[str, str, str, str, str]] = set()
        for source, text in items:
            for item in self.parse_text(text, source=source):
                key = item.game.identity()
                if skip_duplicates and key in seen:
                    continue
                collected.append(item)
                seen.add(key)
        return tuple(collected)

    def create_database(
        self,
        games: Sequence[PgnGame] | Sequence[SourcedPgnGame],
        *,
        skip_duplicates: bool = True,
    ) -> str:
        plain = _plain_games(games)
        merged = merge_pgn_games((), plain, skip_duplicates=skip_duplicates)
        return format_pgn_database(merged)

    def append_to_database(
        self,
        existing_text: str,
        extra: Sequence[PgnGame] | Sequence[SourcedPgnGame],
        *,
        skip_duplicates: bool = True,
    ) -> str:
        current = parse_pgn(existing_text) if existing_text.strip() else ()
        merged = merge_pgn_games(current, _plain_games(extra), skip_duplicates=skip_duplicates)
        return format_pgn_database(merged)

    def added_count(
        self,
        before_text: str,
        after_text: str,
    ) -> int:
        return len(parse_pgn(after_text)) - len(parse_pgn(before_text))


def default_database_filename(exported_at: datetime | None = None) -> str:
    when = exported_at or datetime.now()
    return f"chess-core-{when.strftime('%Y%m%d')}.pgn"


def _plain_games(
    games: Sequence[PgnGame] | Sequence[SourcedPgnGame],
) -> tuple[PgnGame, ...]:
    plain: list[PgnGame] = []
    for item in games:
        if isinstance(item, SourcedPgnGame):
            plain.append(item.game)
        else:
            plain.append(item)
    return tuple(plain)
