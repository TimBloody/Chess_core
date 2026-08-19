"""Duck Chess blocker (duck) placement queries.

Official rules (chess.com, duckchess.com, chessvariants.com):

- Each turn is a standard chess move, then the duck must be moved to any
  empty square. The duck cannot stay on its current square.
- The duck starts off the board. White places it after the first move, on
  any empty square (including the square the mover just vacated).
- The duck is an uncapturable blocker: no piece may land on it or slide
  through it. Knights may jump over it. Occupancy already blocks landing
  and sliding; ``PieceSide.NEUTRAL`` cannot be captured.
- There is no check or checkmate. Kings may move into or through attacked
  squares. The game is won by capturing the enemy king
  (``VictoryKind.KING_CAPTURE``).
- If a player has no legal piece moves at all (even king moves onto
  attacked squares), they are stalemated / "fowled" and they **win**.
  Victory wiring lives outside this module.

``legal_blocker_squares`` / ``legal_blocker_actions`` are meant to be called
on a position **after** the piece move of the current turn has already been
applied, so the mover's origin is empty and is a legal duck destination.
The square the moving piece landed on is occupied and is not legal.
"""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.move import PlaceBlockerAction
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState

BLOCKER_TYPE_NAME = "blocker"


def _is_blocker(piece: Piece | None) -> bool:
    return (
        piece is not None
        and piece.side is PieceSide.NEUTRAL
        and piece.piece_type.name == BLOCKER_TYPE_NAME
    )


def blocker_index(state: GameState) -> int | None:
    """Index of the unique NEUTRAL blocker, or None if off-board.

    Raise ValueError if more than one blocker is present.
    """
    found: int | None = None
    shape = state.board_state.board.shape
    for index in range(shape.cell_count):
        if not _is_blocker(state.board_state.piece_at(index)):
            continue
        if found is not None:
            raise ValueError("expected at most one blocker on the board")
        found = index
    return found


def blocker_square(state: GameState) -> Square | None:
    """Square of the duck, or None if it is off-board."""
    index = blocker_index(state)
    if index is None:
        return None
    shape = state.board_state.board.shape
    return Square.from_index(index, shape.files, shape.ranks)


def legal_blocker_squares(state: GameState) -> list[Square]:
    """Empty squares the duck may be placed on after a piece move.

    Excludes the duck's current square so it must move. If the duck is
    off-board, every empty square is legal. Sorted by ``square.index(files)``.
    """
    shape = state.board_state.board.shape
    files = shape.files
    current = blocker_index(state)
    squares: list[Square] = []
    for index in range(shape.cell_count):
        if index == current:
            continue
        if state.board_state.piece_at(index) is not None:
            continue
        squares.append(Square.from_index(index, files, shape.ranks))
    squares.sort(key=lambda square: square.index(files))
    return squares


def legal_blocker_actions(state: GameState) -> list[PlaceBlockerAction]:
    """``PlaceBlockerAction`` for each ``legal_blocker_squares(state)``."""
    return [PlaceBlockerAction(square) for square in legal_blocker_squares(state)]
