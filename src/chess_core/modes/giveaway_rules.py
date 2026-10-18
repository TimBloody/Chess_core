"""Giveaway / antichess: capture is mandatory when available."""

from __future__ import annotations

from chess_core.core.move import Action, MoveAction
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState


class MustCaptureLegality:
    """If any legal capture exists, quiet moves are discarded."""

    def filter_legal(self, pseudo_moves: list[Action], state: object) -> list[Action]:
        if not isinstance(state, GameState):
            return pseudo_moves
        captures = [
            action
            for action in pseudo_moves
            if isinstance(action, MoveAction) and _is_capture(action, state)
        ]
        return captures or list(pseudo_moves)


def _is_capture(action: MoveAction, state: GameState) -> bool:
    if action.jumped:
        return True
    shape = state.board_state.board.shape
    target = action.to_square.index(shape.files)
    occupant = state.board_state.piece_at(target)
    if occupant is not None and occupant.side is not state.side_to_move:
        return occupant.side is not PieceSide.NEUTRAL
    if action.to_square != state.extras.get("en_passant"):
        return False
    source = action.from_square.index(shape.files)
    piece = state.board_state.piece_at(source)
    return piece is not None and piece.piece_type.name == "pawn"
