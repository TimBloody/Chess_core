"""Pieces, move patterns, and dynamic transforms (e.g. Kyoto flip)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol

from chess_core.core.board import Square


class PieceSide(Enum):
    WHITE = auto()
    BLACK = auto()
    NEUTRAL = auto()

    def opponent(self) -> "PieceSide":
        if self is PieceSide.WHITE:
            return PieceSide.BLACK
        if self is PieceSide.BLACK:
            return PieceSide.WHITE
        raise ValueError("neutral has no opponent")


@dataclass(frozen=True, slots=True)
class PieceTypeId:
    """Stable id for a piece definition in a GameMode catalog."""

    name: str


class MovePatternKind(Enum):
    LEAP = auto()
    SLIDE = auto()
    CUSTOM_MASK = auto()


@dataclass(frozen=True, slots=True)
class MovePattern:
    """How a piece type moves; mask may depend on context via resolver."""

    kind: MovePatternKind
    directions: tuple[tuple[int, int], ...] = ()
    pattern_key: str | None = None


class PieceTransformContext(Protocol):
    def square(self) -> Square:
        pass

    def move_count_for_piece(self) -> int:
        pass

    def game_ply(self) -> int:
        pass


class PieceTransform(ABC):
    """After-move or on-drop change of effective piece type / face."""

    @abstractmethod
    def apply(self, piece_type: PieceTypeId, context: PieceTransformContext) -> PieceTypeId:
        """Return the effective type after a configured transform."""


@dataclass
class PieceType:
    id: PieceTypeId
    patterns: tuple[MovePattern, ...]
    can_promote: bool = False
    transforms_on_move: PieceTransform | None = None


@dataclass
class Piece:
    """Instance on board: type, side, optional face/orientation state."""

    piece_type: PieceTypeId
    side: PieceSide
    state: dict[str, Any] | None = None

    def effective_type(self, context: PieceTransformContext) -> PieceTypeId:
        del context
        return self.piece_type


class PieceCatalog:
    """All piece types for a GameMode."""

    def __init__(self) -> None:
        self._types: dict[str, PieceType] = {}

    def register(self, piece_type: PieceType) -> None:
        name = piece_type.id.name.strip()
        if not name:
            raise ValueError("piece type id must not be empty")
        if name in self._types:
            raise ValueError(f"piece type already registered: {name}")
        self._types[name] = piece_type

    def get(self, type_id: PieceTypeId) -> PieceType:
        try:
            return self._types[type_id.name]
        except KeyError as exc:
            raise KeyError(f"unknown piece type: {type_id.name}") from exc

    def all_types(self) -> tuple[PieceType, ...]:
        return tuple(self._types.values())

    def resolve_move_mask_key(
        self,
        piece: Piece,
        square: Square,
        context: PieceTransformContext,
    ) -> str:
        """Key into prebuilt bit masks for this piece at this context."""
        piece_type = self.get(piece.effective_type(context))
        explicit_keys = {
            pattern.pattern_key for pattern in piece_type.patterns if pattern.pattern_key
        }
        if len(explicit_keys) > 1:
            raise ValueError(
                f"piece type {piece_type.id.name!r} has multiple mask keys"
            )
        return next(iter(explicit_keys), piece_type.id.name)
