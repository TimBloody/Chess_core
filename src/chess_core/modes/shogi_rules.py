"""Shared shogi drop, promotion, and start-cell rules.

Mode factories configure these objects; movegen and state stay variant-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

from functools import lru_cache

from chess_core.core.board import BoardShape, Square
from chess_core.core.piece import Piece, PieceSide, PieceTransform, PieceTypeId
from chess_core.core.rules import drop_square_is_empty
from chess_core.core.state import GameState


def squares_ahead(side: PieceSide, rank: int, ranks: int) -> int:
    """How many ranks remain in the piece's forward direction."""
    return side.ranks_ahead(rank, ranks)


def last_rank_for(side: PieceSide, ranks: int) -> int:
    return side.last_rank(ranks)


@lru_cache(maxsize=64)
def promotion_zone_mask(shape: BoardShape, side: PieceSide, depth: int) -> int:
    """Bitmask of the opponent's nearest ``depth`` ranks for ``side``."""
    depth = max(0, min(depth, shape.ranks))
    ranks = range(depth) if side is PieceSide.BLACK else range(shape.ranks - depth, shape.ranks)
    mask = 0
    for rank in ranks:
        for file in range(shape.files):
            mask |= 1 << (rank * shape.files + file)
    return mask


KYOTO_FLIP_PAIRS = {
    "tokin": "lance",
    "lance": "tokin",
    "silver": "bishop",
    "bishop": "silver",
    "gold": "knight",
    "knight": "gold",
    "pawn": "rook",
    "rook": "pawn",
}


class KyotoFlipTransform(PieceTransform):
    """Flip a Kyoto piece to its alternate face after each board move."""

    def apply(self, piece_type: PieceTypeId, context) -> PieceTypeId:
        del context
        return PieceTypeId(KYOTO_FLIP_PAIRS.get(piece_type.name, piece_type.name))


class KyotoDropRule:
    """Kyoto pieces may be dropped on any empty square with either face up."""

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        del piece_type
        return drop_square_is_empty(state, square_index)

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        paired = KYOTO_FLIP_PAIRS.get(piece_type.name)
        return None if paired is None else (piece_type.name, paired)


def facing_start_cells(
    files: int,
    ranks: int,
    rows_from_back: dict[int, tuple[str | None, ...]],
    *,
    first_side: PieceSide = PieceSide.BLACK,
) -> dict[int, Piece]:
    """Place pieces so the first player sees ``rows_from_back`` from their seat.

    Rank 0 of ``rows_from_back`` is that player's back rank, left-to-right from
    their viewpoint. BLACK sits on the last rank; a 180° view puts them at the
    bottom with file 0 on their right, matching chess coordinates.
    """
    if first_side is not PieceSide.BLACK:
        raise ValueError("shogi start cells currently assume BLACK is sente")
    last = ranks - 1
    cells: dict[int, Piece] = {}
    for rank_from_back, names in rows_from_back.items():
        if len(names) != files:
            raise ValueError("start row width must match board files")
        if not 0 <= rank_from_back < ranks:
            raise ValueError("start rank is outside the board")
        for display_file, name in enumerate(names):
            if not name:
                continue
            black_file = files - 1 - display_file
            black_rank = last - rank_from_back
            cells[black_rank * files + black_file] = Piece(PieceTypeId(name), first_side)
            cells[rank_from_back * files + display_file] = Piece(
                PieceTypeId(name), first_side.opponent()
            )
    return cells


@dataclass(frozen=True)
class ShogiDropRule:
    """Configurable drops: nifu, dead squares, and optional pawn-drop mate ban."""

    nifu: bool = True
    dead_squares: bool = True
    forbid_pawn_drop_mate: bool = True
    pawn_types: frozenset[str] = frozenset({"pawn", "chick"})
    lance_types: frozenset[str] = frozenset({"lance"})
    knight_types: frozenset[str] = frozenset({"knight"})

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        if not isinstance(state, GameState):
            raise TypeError("shogi drops require GameState")
        if not drop_square_is_empty(state, square_index):
            return False
        shape = state.board_state.board.shape
        square = Square.from_index(square_index, shape.files, shape.ranks)
        side = state.side_to_move
        name = piece_type.name
        if self.dead_squares and self._is_dead_square(name, side, square, shape.ranks):
            return False
        if self.nifu and name in self.pawn_types and self._file_has_pawn(state, side, square.file):
            return False
        return True

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def _is_dead_square(
        self, name: str, side: PieceSide, square: Square, ranks: int
    ) -> bool:
        ahead = squares_ahead(side, square.rank, ranks)
        if name in self.pawn_types or name in self.lance_types:
            return ahead == 0
        if name in self.knight_types:
            return ahead < 2
        return False

    def _file_has_pawn(self, state: GameState, side: PieceSide, file: int) -> bool:
        shape = state.board_state.board.shape
        for rank in range(shape.ranks):
            piece = state.board_state.piece_at(rank * shape.files + file)
            if (
                piece is not None
                and piece.side is side
                and piece.piece_type.name in self.pawn_types
            ):
                return True
        return False


@dataclass(frozen=True)
class ShogiPromotionRule:
    """Promote when moving into, within, or out of the opponent's camp."""

    zone_depth: int
    mapping: dict[str, str]
    force_immobile: frozenset[str] = frozenset({"pawn", "lance", "knight", "chick"})

    def promotion_zone_mask(self, side: object) -> int:
        del side
        return 0

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        promoted = self.mapping.get(piece_type.name)
        if promoted is None:
            return ()
        return (PieceTypeId(promoted),)

    def may_promote(
        self,
        piece_type: PieceTypeId,
        from_index: int,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        if piece_type.name not in self.mapping:
            return False
        if not isinstance(state, GameState) or not isinstance(side, PieceSide):
            return False
        shape = state.board_state.board.shape
        origin = Square.from_index(from_index, shape.files, shape.ranks)
        target = Square.from_index(to_index, shape.files, shape.ranks)
        zone = promotion_zone_mask(shape, side, self.zone_depth)
        origin_bit = 1 << origin.index(shape.files)
        target_bit = 1 << target.index(shape.files)
        return bool(origin_bit & zone) or bool(target_bit & zone)

    def must_promote(
        self,
        piece_type: PieceTypeId,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        if piece_type.name not in self.force_immobile:
            return False
        if not isinstance(state, GameState) or not isinstance(side, PieceSide):
            return False
        if piece_type.name not in self.mapping:
            return False
        shape = state.board_state.board.shape
        target = Square.from_index(to_index, shape.files, shape.ranks)
        ahead = side.ranks_ahead(target.rank, shape.ranks)
        if piece_type.name in {"knight"}:
            return ahead < 2
        return ahead == 0


STANDARD_SHOGI_PROMOTIONS = {
    "pawn": "tokin",
    "lance": "promoted_lance",
    "knight": "promoted_knight",
    "silver": "promoted_silver",
    "bishop": "horse",
    "rook": "dragon",
}

DOBUTSU_PROMOTIONS = {"chick": "hen"}
