"""Chess promotion configured as a PromotionRule, not movegen branches."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.board import Square
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.core.state import GameState


@dataclass(frozen=True)
class ChessPromotionRule:
    """Pawns reaching the last rank must promote to a major/minor piece."""

    piece_name: str = "pawn"
    choices_names: tuple[str, ...] = ("queen", "rook", "bishop", "knight")

    def promotion_zone_mask(self, side: object) -> int:
        del side
        return 0

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        if piece_type.name != self.piece_name:
            return ()
        return tuple(PieceTypeId(name) for name in self.choices_names)

    def may_promote(
        self,
        piece_type: PieceTypeId,
        from_index: int,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        del from_index
        return self.must_promote(piece_type, to_index, side, state)

    def must_promote(
        self,
        piece_type: PieceTypeId,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        if piece_type.name != self.piece_name:
            return False
        if not isinstance(state, GameState) or not isinstance(side, PieceSide):
            return False
        shape = state.board_state.board.shape
        target = Square.from_index(to_index, shape.files, shape.ranks)
        return target.rank == side.last_rank(shape.ranks)
