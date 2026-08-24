"""Crazyhouse drop restrictions and capture demotion helpers.

Wired by GameMode.drop_rule / CaptureSink — not by ``if mode.id == ...``.
"""

from __future__ import annotations

from copy import deepcopy

from chess_core.core.piece import Piece, PieceTypeId
from chess_core.core.rules import DropRule
from chess_core.core.state import GameState


class CrazyhouseDropRule(DropRule):
    """Orthodox chess plus drops from a hand.

    Pawns may not be dropped on the first or last rank. Other types may drop
    on any empty square. Promoted captures demote via ``captured_as``.
    """

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        if not isinstance(state, GameState):
            return False
        if state.board_state.piece_at(square_index) is not None:
            return False
        shape = state.board_state.board.shape
        rank = square_index // shape.files
        if piece_type.name == "pawn" and rank in {0, shape.ranks - 1}:
            return False
        return True

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def captured_as(self, piece: Piece) -> Piece:
        return demote_captured_piece(piece)


def demote_captured_piece(piece: Piece) -> Piece:
    """Promoted chess pieces return to the pocket as their unpromoted type."""
    result = deepcopy(piece)
    origin = None
    if result.state:
        origin = result.state.get("promoted_from")
    if origin:
        result.piece_type = PieceTypeId(str(origin))
    if result.state:
        result.state = {key: value for key, value in result.state.items() if key != "promoted_from"}
        if not result.state:
            result.state = None
    return result
