"""Atomic actions and composed player turns."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chess_core.core.board import Square
from chess_core.core.piece import PieceSide, PieceTypeId


class ActionKind(Enum):
    MOVE_PIECE = auto()
    DROP_PIECE = auto()
    PLACE_PIECE = auto()
    TRANSFORM_PIECE = auto()
    PLACE_BLOCKER = auto()
    PASS = auto()


@dataclass(frozen=True, slots=True)
class MoveAction:
    from_square: Square
    to_square: Square
    promotion_choice: PieceTypeId | None = None
    path: tuple[Square, ...] = ()
    captured_squares: tuple[Square, ...] = ()

    @property
    def kind(self) -> ActionKind:
        return ActionKind.MOVE_PIECE


@dataclass(frozen=True, slots=True)
class DropAction:
    piece_type: PieceTypeId
    to_square: Square
    face: str | None = None

    @property
    def kind(self) -> ActionKind:
        return ActionKind.DROP_PIECE


@dataclass(frozen=True, slots=True)
class PlaceAction:
    """Place a piece type onto a square (gomoku, reversi, gobblet reserve)."""

    piece_type: PieceTypeId
    to_square: Square
    face: str | None = None

    @property
    def kind(self) -> ActionKind:
        return ActionKind.PLACE_PIECE


@dataclass(frozen=True, slots=True)
class TransformAction:
    square: Square
    new_type: PieceTypeId

    @property
    def kind(self) -> ActionKind:
        return ActionKind.TRANSFORM_PIECE


@dataclass(frozen=True, slots=True)
class PlaceBlockerAction:
    """Duck chess: place duck on empty square after piece move."""

    square: Square

    @property
    def kind(self) -> ActionKind:
        return ActionKind.PLACE_BLOCKER


@dataclass(frozen=True, slots=True)
class PassAction:
    @property
    def kind(self) -> ActionKind:
        return ActionKind.PASS


Action = (
    MoveAction
    | DropAction
    | PlaceAction
    | TransformAction
    | PlaceBlockerAction
    | PassAction
)


@dataclass
class Turn:
    """One player's full turn: ordered list of actions per TurnScenario."""

    side: PieceSide
    actions: list[Action]

    def is_complete(self) -> bool:
        return bool(self.actions)
