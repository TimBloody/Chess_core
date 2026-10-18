"""54-bit Gobblet encoding (possiblywrong): 6 bits per square, sizes 332211.

Each size uses 2 bits: 00 empty, 01 side to move, 10 opponent. Reserve is
implied (two of each size per player). After a move the colours are swapped
so it is always 01 to move.
"""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.state import GameState
from chess_core.modes.gobblet_rules import GOBBLET_SIZES, stack_at

STM = 1
OPP = 2
STATE_MASK = (1 << 54) - 1
NUM_PER_SIZE = 2

LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

# Center, then corners, then sides.
SQUARE_WEIGHT: tuple[int, ...] = (2, 1, 2, 1, 4, 1, 2, 1, 2)

SIZE_NAMES = ("gobblet_small", "gobblet_medium", "gobblet_large")
_SWAP_OPP = 0x2AAAAAAAAAAAAA
_SWAP_STM = 0x15555555555555


@dataclass(frozen=True, slots=True)
class NativeMove:
    """start < 0 is a drop of size -start (1 small .. 3 large)."""

    start: int
    end: int

    @property
    def size(self) -> int:
        if self.start < 0:
            return -self.start
        return 0


def square_cell(state: int, square: int) -> int:
    return (state >> (6 * square)) & 0x3F


def top_owner_size(cell: int) -> tuple[int, int]:
    owner = 0
    size = 0
    pieces = cell
    while pieces:
        owner = pieces & 3
        pieces >>= 2
        size += 1
    return owner, size


def can_cover(cell: int, size: int) -> bool:
    return (1 << (2 * (size - 1))) > cell


def swap(state: int) -> int:
    return ((state & _SWAP_OPP) >> 1) | ((state & _SWAP_STM) << 1)


def apply_move(state: int, move: NativeMove, size: int) -> int:
    result = state
    if move.start >= 0:
        result ^= 1 << (6 * move.start + 2 * (size - 1))
    return result ^ (1 << (6 * move.end + 2 * (size - 1)))


def played_counts(state: int, who: int = STM) -> list[int]:
    counts = [0, 0, 0]
    for square in range(9):
        cell = square_cell(state, square)
        for size in range(3):
            if ((cell >> (2 * size)) & 3) == who:
                counts[size] += 1
    return counts


def encode_state(game: GameState) -> int:
    """Pack a GameState into a 54-bit stm-relative key."""
    stm = game.side_to_move
    bits = 0
    for square in range(9):
        cell = 0
        for piece in stack_at(game, square):
            size = GOBBLET_SIZES[piece.piece_type.name]
            owner = STM if piece.side is stm else OPP
            cell |= owner << (2 * (size - 1))
        bits |= cell << (6 * square)
    return bits


def terminal_value(state: int) -> int:
    """+1 if side to move already has a line, -1 if opponent does, else 0.

    Opponent line is scored even if we also have one: uncovering their triple
    loses unless we filtered that lift as illegal.
    """
    stm_line = False
    opp_line = False
    for line in LINES:
        owners: list[int] = []
        broken = False
        for square in line:
            owner, _size = top_owner_size(square_cell(state, square))
            if owner == 0:
                broken = True
                break
            owners.append(owner)
        if broken:
            continue
        if owners[0] == owners[1] == owners[2] == STM:
            stm_line = True
        elif owners[0] == owners[1] == owners[2] == OPP:
            opp_line = True
    if stm_line:
        return 1
    if opp_line:
        return -1
    return 0


def opponent_lines(state: int) -> tuple[tuple[int, int, int], ...]:
    found: list[tuple[int, int, int]] = []
    for line in LINES:
        owners = []
        ok = True
        for square in line:
            owner, _size = top_owner_size(square_cell(state, square))
            if owner != OPP:
                ok = False
                break
            owners.append(owner)
        if ok:
            found.append(line)
    return tuple(found)
