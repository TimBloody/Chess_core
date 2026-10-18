"""Shared helpers for orthogonal line games with custodian-style capture."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState

ORTHOGONALS = ((0, 1), (0, -1), (1, 0), (-1, 0))


def opponent(side: PieceSide) -> PieceSide:
    return PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE


def piece_count(state: GameState, side: PieceSide) -> int:
    return sum(
        1
        for piece in state.board_state.cells.values()
        if piece is not None and piece.side is side
    )


def line_indices_for_square(
    state: GameState, square: Square, *, horizontal: bool
) -> tuple[int, ...]:
    shape = state.board_state.board.shape
    files = shape.files
    if horizontal:
        rank = square.rank
        return tuple(rank * files + file for file in range(files))
    file = square.file
    return tuple(rank * files + file for rank in range(shape.ranks))


def lines_through_square(state: GameState, square: Square) -> tuple[tuple[int, ...], ...]:
    return (
        line_indices_for_square(state, square, horizontal=True),
        line_indices_for_square(state, square, horizontal=False),
    )


def piece_at(state: GameState, index: int) -> Piece | None:
    return state.board_state.piece_at(index)


def nanai_captures_after_move(
    state: GameState,
    *,
    from_index: int,
    to_index: int,
    side: PieceSide,
) -> tuple[int, ...]:
    """Capture opponent when the move completes own-own-opponent on a line."""
    files = state.board_state.board.shape.files
    to_square = Square.from_index(
        to_index,
        files,
        state.board_state.board.shape.ranks,
    )
    captures: set[int] = set()
    foe = opponent(side)
    for line in lines_through_square(state, to_square):
        for position, index in enumerate(line):
            victim = piece_at(state, index)
            if victim is None or victim.side is not foe:
                continue
            if position < 2:
                continue
            first_own = piece_at(state, line[position - 1])
            second_own = piece_at(state, line[position - 2])
            if first_own is None or second_own is None:
                continue
            if first_own.side is not side or second_own.side is not side:
                continue
            if position >= 3:
                third = piece_at(state, line[position - 3])
                if third is not None and third.side is side:
                    continue
            if to_index not in {line[position - 1], line[position - 2]}:
                continue
            captures.add(index)
    return tuple(sorted(captures))


def hasami_captures_after_move(
    state: GameState,
    *,
    from_index: int,
    to_index: int,
    side: PieceSide,
) -> tuple[int, ...]:
    """Custodian capture: bracket opponent piece(s) between two own on a line."""
    files = state.board_state.board.shape.files
    to_square = Square.from_index(
        to_index,
        files,
        state.board_state.board.shape.ranks,
    )
    captures: set[int] = set()
    foe = opponent(side)
    for line in lines_through_square(state, to_square):
        for left in range(len(line)):
            left_piece = piece_at(state, line[left])
            if left_piece is None or left_piece.side is not side:
                continue
            for right in range(left + 2, len(line)):
                right_piece = piece_at(state, line[right])
                if right_piece is None or right_piece.side is not side:
                    continue
                if line[left] not in {from_index, to_index} and line[right] not in {
                    from_index,
                    to_index,
                }:
                    continue
                between = line[left + 1 : right]
                if not between:
                    continue
                occupied = [
                    index for index in between if piece_at(state, index) is not None
                ]
                victims = [
                    index
                    for index in occupied
                    if piece_at(state, index) is not None
                    and piece_at(state, index).side is foe
                ]
                if len(victims) != len(occupied):
                    continue
                if victims:
                    captures.update(victims)
    return tuple(sorted(captures))


class LineCaptureTransition:
    """Remove custodian / Nanai victims after a quiet orthogonal move."""

    def __init__(self, style: str) -> None:
        if style not in {"nanai", "hasami"}:
            raise ValueError(f"unknown line-capture style: {style}")
        self._style = style

    def apply_after_action(self, action, state: object) -> object:
        if not isinstance(action, MoveAction) or not isinstance(state, GameState):
            return state
        files = state.board_state.board.shape.files
        from_index = action.from_square.index(files)
        to_index = action.to_square.index(files)
        mover = state.board_state.piece_at(to_index)
        if mover is None:
            return state
        if self._style == "nanai":
            victims = nanai_captures_after_move(
                state, from_index=from_index, to_index=to_index, side=mover.side
            )
        else:
            victims = hasami_captures_after_move(
                state, from_index=from_index, to_index=to_index, side=mover.side
            )
        for index in victims:
            state.board_state.cells[index] = None
        return state
