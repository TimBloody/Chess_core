"""Position search over a PGN database, including move-order transpositions.

ChessBase-style lookup: replay each game once into an inverted index keyed by
the position identity (pieces, side to move, pockets, castling, a real en
passant). Halfmove clocks and move numbers are not part of that identity, so
the same position reached by a different move order is one key.

A query is a dict lookup. SAN resolution is cached by ``(position, token)``
while the index is built, so repeated openings are not regenerated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chess_core.app.pgn_replay import _move_body, resolve_turn, structural_tokens
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import parse_fen
from chess_core.core.pgn import PgnGame
from chess_core.core.repetition import PositionKey, position_key
from chess_core.core.state import GameState


@dataclass(frozen=True, slots=True)
class PositionHit:
    """First time ``game_index`` reached the queried position.

    ``ply`` is the main-line half-move (``0`` is the start) when
    ``on_mainline`` is true, so the board can jump straight there.
    A hit that exists only inside a ``()`` variation keeps the ply of the
    main-line position the variation branches from; the linear board cannot
    show that sideline.
    """

    game_index: int
    ply: int
    on_mainline: bool = True


_NO_HITS: tuple[PositionHit, ...] = ()


class PositionIndex:
    """Inverted index: position identity → games that reached it."""

    def __init__(
        self,
        buckets: dict[PositionKey, tuple[PositionHit, ...]],
        *,
        game_count: int,
    ) -> None:
        self._buckets = buckets
        self.game_count = game_count
        self.position_count = len(buckets)

    def find(self, state: GameState) -> tuple[PositionHit, ...]:
        """Games whose tree contains ``state``, regardless of move order."""
        return self._buckets.get(position_key(state), _NO_HITS)


def build_position_index(
    games: Sequence[PgnGame],
    mode: GameMode,
) -> PositionIndex:
    """Replay ``games`` once under ``mode`` and index every reached position."""
    generator = MoveGenerator(mode)
    start = mode.initial_state()
    turn_cache: dict[tuple[PositionKey, str], Turn | None] = {}
    buckets: dict[PositionKey, list[PositionHit]] = {}
    for game_index, game in enumerate(games):
        try:
            found = _index_game(game, game_index, mode, generator, start, turn_cache)
        except ValueError:
            continue
        for key, hit in found.items():
            buckets.setdefault(key, []).append(hit)
    frozen = {key: tuple(hits) for key, hits in buckets.items()}
    return PositionIndex(frozen, game_count=len(games))


def _index_game(
    game: PgnGame,
    game_index: int,
    mode: GameMode,
    generator: MoveGenerator,
    start: GameState,
    turn_cache: dict[tuple[PositionKey, str], Turn | None],
) -> dict[PositionKey, PositionHit]:
    fen = game.tag("FEN")
    if fen:
        state = parse_fen(fen, mode)
    else:
        state = start
    tokens = structural_tokens(game.moves)
    found: dict[PositionKey, PositionHit] = {}

    def remember(key: PositionKey, ply: int, on_mainline: bool) -> None:
        current = found.get(key)
        if current is None or (on_mainline and not current.on_mainline):
            found[key] = PositionHit(game_index, ply, on_mainline)

    def play(state: GameState, key: PositionKey, token: str) -> GameState | None:
        cache_key = (key, token)
        if cache_key not in turn_cache:
            try:
                turn_cache[cache_key] = resolve_turn(state, token, generator)
            except ValueError:
                turn_cache[cache_key] = None
        cached = turn_cache[cache_key]
        if cached is None:
            return None
        try:
            return state.apply_turn(cached, record_history=False)
        except ValueError:
            return None

    def walk(pos: int, state: GameState, ply: int, *, on_mainline: bool) -> int:
        key = position_key(state)
        remember(key, ply, on_mainline)
        previous = state
        previous_ply = ply
        while pos < len(tokens):
            token = tokens[pos]
            if token == ")":
                return pos + 1
            if token == "(":
                pos = walk(pos + 1, previous, previous_ply, on_mainline=False)
                continue
            pos += 1
            body = _move_body(token)
            if not body:
                continue
            nxt = play(state, key, body)
            if nxt is None:
                if on_mainline:
                    return len(tokens)
                return _skip_variation(tokens, pos)
            previous = state
            previous_ply = ply
            state = nxt
            if on_mainline:
                ply += 1
            key = position_key(state)
            remember(key, ply if on_mainline else previous_ply, on_mainline)
        return pos

    walk(0, state, 0, on_mainline=True)
    return found


def _skip_variation(tokens: Sequence[str], pos: int) -> int:
    """Drop the rest of the current variation after an illegal move."""
    depth = 1
    while pos < len(tokens):
        token = tokens[pos]
        pos += 1
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            if depth == 0:
                return pos
    return pos
