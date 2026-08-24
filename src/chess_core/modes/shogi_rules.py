"""Shogi and dobutsu drop/promotion rules configured on GameMode."""

from __future__ import annotations

from copy import deepcopy

from chess_core.core.board import Square
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState

_SHOGI_PROMOTED = {
    "pawn": "tokin",
    "lance": "promoted_lance",
    "knight": "promoted_knight",
    "silver": "promoted_silver",
    "bishop": "horse",
    "rook": "dragon",
}

_SHOGI_DEMOTE = {promoted: origin for origin, promoted in _SHOGI_PROMOTED.items()}


class ShogiPromotionRule:
    """Last three ranks; optional promote except pawn/lance/knight on the edge."""

    _forced = {
        "pawn": 1,
        "lance": 1,
        "knight": 2,
    }

    def promotion_zone_mask(self, side: str) -> int:
        del side
        return 0

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        promoted = _SHOGI_PROMOTED.get(piece_type.name)
        if promoted is None:
            return ()
        return (PieceTypeId(promoted),)

    def can_promote(
        self,
        piece: Piece,
        origin: Square,
        target: Square,
        state: object,
    ) -> bool:
        if piece.piece_type.name not in _SHOGI_PROMOTED:
            return False
        if not isinstance(state, GameState):
            return False
        ranks = state.board_state.board.shape.ranks
        return _in_promotion_zone(piece.side, origin.rank, ranks, depth=3) or _in_promotion_zone(
            piece.side, target.rank, ranks, depth=3
        )

    def must_promote(
        self,
        piece: Piece,
        origin: Square,
        target: Square,
        state: object,
    ) -> bool:
        del origin
        depth = self._forced.get(piece.piece_type.name)
        if depth is None or not isinstance(state, GameState):
            return False
        ranks = state.board_state.board.shape.ranks
        return _in_promotion_zone(piece.side, target.rank, ranks, depth=depth)


class ShogiDropRule:
    """Empty square, nifu, last-rank restrictions; utifudo is filtered in movegen."""

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        if not isinstance(state, GameState):
            return False
        if state.board_state.piece_at(square_index) is not None:
            return False
        shape = state.board_state.board.shape
        rank = square_index // shape.files
        file = square_index % shape.files
        side = state.side_to_move
        if piece_type.name == "pawn" and _file_has_unpromoted_pawn(state, side, file):
            return False
        forbidden = _drop_forbidden_ranks(piece_type.name, side, shape.ranks)
        return rank not in forbidden

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def captured_as(self, piece: Piece) -> Piece:
        return _demote_named(piece, _SHOGI_DEMOTE)

    def forbids_checkmate_drop(self, piece_type: PieceTypeId) -> bool:
        return piece_type.name == "pawn"


class DobutsuPromotionRule:
    """Chick reaching the last rank becomes a hen."""

    def promotion_zone_mask(self, side: str) -> int:
        del side
        return 0

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        if piece_type.name != "chick":
            return ()
        return (PieceTypeId("hen"),)

    def can_promote(
        self,
        piece: Piece,
        origin: Square,
        target: Square,
        state: object,
    ) -> bool:
        return self.must_promote(piece, origin, target, state)

    def must_promote(
        self,
        piece: Piece,
        origin: Square,
        target: Square,
        state: object,
    ) -> bool:
        del origin
        if piece.piece_type.name != "chick" or not isinstance(state, GameState):
            return False
        ranks = state.board_state.board.shape.ranks
        return _in_promotion_zone(piece.side, target.rank, ranks, depth=1)


class DobutsuDropRule:
    """Any empty square; a hen returns to hand as a chick."""

    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        del piece_type
        if not isinstance(state, GameState):
            return False
        return state.board_state.piece_at(square_index) is None

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def captured_as(self, piece: Piece) -> Piece:
        return _demote_named(piece, {"hen": "chick"})


def _demote_named(piece: Piece, mapping: dict[str, str]) -> Piece:
    result = deepcopy(piece)
    origin = mapping.get(result.piece_type.name)
    if result.state:
        origin = origin or result.state.get("promoted_from")
        result.state = {
            key: value for key, value in result.state.items() if key != "promoted_from"
        } or None
    if origin:
        result.piece_type = PieceTypeId(str(origin))
    return result


def _in_promotion_zone(side: PieceSide, rank: int, ranks: int, *, depth: int) -> bool:
    if side is PieceSide.WHITE:
        return rank >= ranks - depth
    return rank < depth


def _file_has_unpromoted_pawn(state: GameState, side: PieceSide, file: int) -> bool:
    shape = state.board_state.board.shape
    for index, piece in state.board_state.cells.items():
        if piece is None or piece.side is not side:
            continue
        if piece.piece_type.name == "pawn" and index % shape.files == file:
            return True
    return False


def _drop_forbidden_ranks(name: str, side: PieceSide, ranks: int) -> set[int]:
    if name == "pawn" or name == "lance":
        edge = ranks - 1 if side is PieceSide.WHITE else 0
        return {edge}
    if name == "knight":
        if side is PieceSide.WHITE:
            return {ranks - 1, ranks - 2}
        return {0, 1}
    return set()
