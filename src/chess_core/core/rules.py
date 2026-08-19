"""Victory, drops, promotion, legality, state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from chess_core.core.board import Square
from chess_core.core.move import Action, MoveAction
from chess_core.core.piece import PieceTypeId


class VictoryKind(Enum):
    CHECKMATE = auto()
    KING_CAPTURE = auto()
    KING_REACHES_ZONE = auto()
    THREE_CHECK = auto()
    STALEMATE = auto()
    MATERIAL = auto()
    RESIGNATION = auto()
    CUSTOM = auto()


@dataclass(frozen=True, slots=True)
class VictoryCondition:
    kind: VictoryKind
    target_zone_mask: int | None = None
    lose_on_no_legal_moves: bool = True
    threshold: int | None = None


def drop_square_is_empty(state: object, square_index: int) -> bool:
    """True when ``square_index`` is on the board and unoccupied."""
    board_state = getattr(state, "board_state", None)
    if board_state is None:
        return False
    shape = board_state.board.shape
    if not 0 <= square_index < shape.cell_count:
        return False
    return board_state.piece_at(square_index) is None


class DropRule(Protocol):
    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        pass

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        """None = single face; tuple = Kyoto-style choose side up."""
        pass


class PromotionRule(Protocol):
    def promotion_zone_mask(self, side: object) -> int:
        pass

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        pass

    def may_promote(
        self,
        piece_type: PieceTypeId,
        from_index: int,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        pass

    def must_promote(
        self,
        piece_type: PieceTypeId,
        to_index: int,
        side: object,
        state: object,
    ) -> bool:
        pass


class LegalityRule(Protocol):
    def filter_legal(self, pseudo_moves: list[Action], state: object) -> list[Action]:
        pass


class MoveProvider(Protocol):
    """Generate mode-specific moves which do not fit leap/slide patterns."""

    def pseudo_legal(self, state: object) -> list[Action]:
        pass


class StateTransitionRule(Protocol):
    def apply_after_action(self, action: Action, state: object) -> object:
        pass


@dataclass(frozen=True, slots=True)
class CastlingPath:
    """One configured castling manoeuvre (classic or Chess960).

    ``vacant_files`` must be empty except the king and the castling rook.
    ``king_path_files`` are squares the king occupies during the manoeuvre,
    including the destination and excluding the origin; they must not be
    attacked. Encoding of the player move is ``MoveAction(king_from, king_to)``
    unless ``king_from == king_to``, in which case it is
    ``MoveAction(king_from, rook_from)`` (Chess960 UCI).
    """

    right: str
    king_from: Square
    king_to: Square
    rook_from: Square
    rook_to: Square
    vacant_files: tuple[int, ...]
    king_path_files: tuple[int, ...]


class CastlingRule(Protocol):
    def paths(self, state: object, side: object) -> tuple[CastlingPath, ...]:
        """Candidate paths; movegen still checks emptiness, rights, and checks."""

    def decode(self, action: MoveAction, state: object) -> CastlingPath | None:
        """Return the path when ``action`` is this side's castling move."""
