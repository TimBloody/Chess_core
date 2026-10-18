"""D4 board symmetries: perceive Gobblet in a fixed orientation.

Empty squares are scored toward the top-right (c3). Equivalent positions
collapse to one 54-bit key so the opening book and search TT share work.
"""

from __future__ import annotations

from chess_core.app.gobblet_engine.bits import NativeMove, square_cell

_D4: tuple[tuple[int, ...], ...]


def _coord_perm(transform) -> tuple[int, ...]:
    perm = [0] * 9
    for index in range(9):
        file, rank = index % 3, index // 3
        new_file, new_rank = transform(file, rank)
        perm[index] = new_rank * 3 + new_file
    return tuple(perm)


_D4 = (
    _coord_perm(lambda file, rank: (file, rank)),
    _coord_perm(lambda file, rank: (rank, 2 - file)),
    _coord_perm(lambda file, rank: (2 - file, 2 - rank)),
    _coord_perm(lambda file, rank: (2 - rank, file)),
    _coord_perm(lambda file, rank: (2 - file, rank)),
    _coord_perm(lambda file, rank: (file, 2 - rank)),
    _coord_perm(lambda file, rank: (rank, file)),
    _coord_perm(lambda file, rank: (2 - rank, 2 - file)),
)


def d4_perms() -> tuple[tuple[int, ...], ...]:
    return _D4


def invert_perm(perm: tuple[int, ...]) -> tuple[int, ...]:
    inverse = [0] * 9
    for src, dst in enumerate(perm):
        inverse[dst] = src
    return tuple(inverse)


def transform_state(state: int, perm: tuple[int, ...]) -> int:
    result = 0
    for src in range(9):
        result |= square_cell(state, src) << (6 * perm[src])
    return result


def map_move(move: NativeMove, perm: tuple[int, ...]) -> NativeMove:
    end = perm[move.end]
    if move.start < 0:
        return NativeMove(move.start, end)
    return NativeMove(perm[move.start], end)


def empty_top_right_score(state: int) -> int:
    """Prefer empty cells toward c3 (file 2, rank 2)."""
    score = 0
    for index in range(9):
        if square_cell(state, index) == 0:
            file, rank = index % 3, index // 3
            score += (file + 1) * (rank + 1)
    return score


def canonical(state: int) -> tuple[int, tuple[int, ...]]:
    """Return (oriented state, perm original→canonical)."""
    best_state = state
    best_perm = _D4[0]
    best_key = (empty_top_right_score(state), -state)
    for perm in _D4[1:]:
        oriented = transform_state(state, perm)
        key = (empty_top_right_score(oriented), -oriented)
        if key > best_key:
            best_key = key
            best_state = oriented
            best_perm = perm
    return best_state, best_perm


def canonical_key(state: int) -> int:
    return canonical(state)[0]
