"""Victory, drops, promotion, legality, state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from chess_core.core.move import Action
from chess_core.core.piece import PieceTypeId


class VictoryKind(Enum):
    CHECKMATE = auto()
    KING_CAPTURE = auto()
    KING_REACHES_ZONE = auto()
    STALEMATE = auto()
    MATERIAL = auto()
    RESIGNATION = auto()
    CUSTOM = auto()


@dataclass(frozen=True, slots=True)
class VictoryCondition:
    kind: VictoryKind
    target_zone_mask: int | None = None
    lose_on_no_legal_moves: bool = True


class DropRule(Protocol):
    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        pass

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        """None = single face; tuple = Kyoto-style choose side up."""
        pass


class PromotionRule(Protocol):
    def promotion_zone_mask(self, side: str) -> int:
        pass

    def choices(self, piece_type: PieceTypeId) -> tuple[PieceTypeId, ...]:
        pass


class LegalityRule(Protocol):
    def filter_legal(self, pseudo_moves: list[Action], state: object) -> list[Action]:
        pass


class StateTransitionRule(Protocol):
    def apply_after_action(self, action: Action, state: object) -> object:
        pass
