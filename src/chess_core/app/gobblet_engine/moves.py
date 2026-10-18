"""Bitboard move generation for Gobblet, including hail-mary lifts."""

from __future__ import annotations

from chess_core.app.gobblet_engine.bits import (
    NativeMove,
    NUM_PER_SIZE,
    can_cover,
    opponent_lines,
    played_counts,
    square_cell,
    top_owner_size,
    STM,
)


def move_size(state: int, move: NativeMove) -> int:
    if move.start < 0:
        return -move.start
    _owner, size = top_owner_size(square_cell(state, move.start))
    return size


def lift(state: int, start: int, size: int) -> int:
    return state ^ (1 << (6 * start + 2 * (size - 1)))


def legal_moves(state: int) -> list[NativeMove]:
    moves: list[NativeMove] = []
    played = played_counts(state)
    for start in range(9):
        cell = square_cell(state, start)
        owner, size = top_owner_size(cell)
        if owner != STM or size == 0:
            continue
        revealed = opponent_lines(lift(state, start, size))
        if revealed:
            destinations = {
                index
                for line in revealed
                for index in line
                if index != start
            }
        else:
            destinations = set(range(9)) - {start}
        for end in sorted(destinations):
            if can_cover(square_cell(state, end), size):
                moves.append(NativeMove(start, end))
    for size in (1, 2, 3):
        if played[size - 1] >= NUM_PER_SIZE:
            continue
        for end in range(9):
            if can_cover(square_cell(state, end), size):
                moves.append(NativeMove(-size, end))
    return moves


def can_place(state: int, dest: int, min_size: int) -> bool:
    """True if STM can drop or slide a piece of size >= min_size onto dest."""
    dest_cell = square_cell(state, dest)
    played = played_counts(state)
    for size in range(max(min_size, 1), 4):
        if played[size - 1] < NUM_PER_SIZE and can_cover(dest_cell, size):
            return True
    for start in range(9):
        if start == dest:
            continue
        owner, size = top_owner_size(square_cell(state, start))
        if owner != STM or size < min_size or not can_cover(dest_cell, size):
            continue
        revealed = opponent_lines(lift(state, start, size))
        if revealed:
            allowed = {index for line in revealed for index in line}
            if dest not in allowed:
                continue
        return True
    return False
