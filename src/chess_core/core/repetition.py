"""Threefold repetition: position identity shared by every playable mode.

A position matches a previous one only when all of these agree:

- side to move
- pieces on every square, including hidden Gobblet stacks
- pockets / hands (shogi, crazyhouse, Gobblet reserve)
- castling rights (the right itself, even if currently blocked)
- a legal-looking en passant capture (ignored if no pawn can take)

Halfmove clocks and move numbers are not part of the identity.
"""

from __future__ import annotations

from collections import Counter

from chess_core.core.board import Square
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState

THREEFOLD = 3

PositionKey = tuple[
    str,
    tuple[tuple[int, tuple[tuple[str, str], ...]], ...],
    tuple[tuple[str, str, int], ...],
    tuple[str, ...],
    tuple[tuple[str, int], ...],
    tuple[int, int] | None,
]


def position_key(state: GameState) -> PositionKey:
    """Hashable snapshot of everything that can still change legal moves."""
    return (
        state.side_to_move.name,
        _occupancy_key(state),
        _pockets_key(state),
        _castling_rights_key(state),
        _castling_rooks_key(state),
        _en_passant_key(state),
    )


def seed_repetition_log(state: GameState) -> GameState:
    """Treat ``state`` as the first occurrence of its current position."""
    state.repetition_log = (position_key(state),)
    return state


def repetition_count(state: GameState) -> int:
    """How many times the live position has appeared, including now."""
    current = position_key(state)
    log = state.repetition_log
    if not log:
        return 1
    count = log.count(current)
    if log[-1] != current:
        count += 1
    return count


def is_threefold(state: GameState) -> bool:
    return repetition_count(state) >= THREEFOLD


def _piece_id(piece: Piece) -> tuple[str, str]:
    return (piece.piece_type.name, piece.side.name)


def _occupancy_key(state: GameState) -> tuple[tuple[int, tuple[tuple[str, str], ...]], ...]:
    extras = state.extras
    cell_count = state.board_state.board.shape.cell_count
    stacks = extras.get("stacks")
    if extras.get("stack_covers") or isinstance(stacks, dict):
        raw_stacks = stacks if isinstance(stacks, dict) else {}
        items: list[tuple[int, tuple[tuple[str, str], ...]]] = []
        for index in range(cell_count):
            stack = _stack_at(state, raw_stacks, index)
            if stack:
                items.append((index, stack))
        return tuple(items)
    occupied: list[tuple[int, tuple[tuple[str, str], ...]]] = []
    for index in range(cell_count):
        piece = state.board_state.piece_at(index)
        if piece is not None:
            occupied.append((index, (_piece_id(piece),)))
    return tuple(occupied)


def _stack_at(
    state: GameState,
    stacks: dict[object, object],
    index: int,
) -> tuple[tuple[str, str], ...]:
    raw = stacks.get(index)
    if raw is None:
        raw = stacks.get(str(index))
    if isinstance(raw, (list, tuple)):
        return tuple(_piece_id(piece) for piece in raw if isinstance(piece, Piece))
    piece = state.board_state.piece_at(index)
    if piece is None:
        return ()
    return (_piece_id(piece),)


def _pockets_key(state: GameState) -> tuple[tuple[str, str, int], ...]:
    if state.hands is None:
        return ()
    counts: Counter[tuple[str, str]] = Counter()
    for side, pieces in state.hands.by_side.items():
        side_name = side.name if isinstance(side, PieceSide) else str(side)
        for piece in pieces:
            counts[(side_name, piece.piece_type.name)] += 1
    return tuple(sorted((side, name, count) for (side, name), count in counts.items() if count))


def _castling_rights_key(state: GameState) -> tuple[str, ...]:
    rights = set(state.extras.get("castling_rights") or ())
    known = tuple(flag for flag in "KQkq" if flag in rights)
    extra = tuple(sorted(str(flag) for flag in rights if str(flag) not in set("KQkq")))
    return known + extra


def _castling_rooks_key(state: GameState) -> tuple[tuple[str, int], ...]:
    rooks = state.extras.get("castling_rooks")
    if not isinstance(rooks, dict):
        return ()
    items: list[tuple[str, int]] = []
    for flag, file in rooks.items():
        try:
            items.append((str(flag), int(file)))
        except (TypeError, ValueError):
            continue
    return tuple(sorted(items))


def _en_passant_key(state: GameState) -> tuple[int, int] | None:
    """Include EP only when a pawn of the side to move can capture onto it.

    A double-step that nobody can actually take does not distinguish positions
    (FIDE 9.2). Pin legality is not required: an adjacent capturing pawn is
    enough for the *possibility* to differ.
    """
    square = state.extras.get("en_passant")
    if not isinstance(square, Square):
        return None
    shape = state.board_state.board.shape
    direction = 1 if state.side_to_move is PieceSide.WHITE else -1
    origin_rank = square.rank - direction
    if not 0 <= origin_rank < shape.ranks:
        return None
    for file_delta in (-1, 1):
        origin_file = square.file + file_delta
        if not 0 <= origin_file < shape.files:
            continue
        origin = Square(origin_file, origin_rank)
        piece = state.board_state.piece_at(origin.index(shape.files))
        if (
            piece is not None
            and piece.side is state.side_to_move
            and piece.piece_type.name == "pawn"
        ):
            return (square.file, square.rank)
    return None
