"""Normalized legal-turn options for UI and application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chess_core.core.move import (
    DropAction,
    MoveAction,
    PlaceAction,
    Turn,
)
from chess_core.core.notation import NotationStyle
from chess_core.core.piece import PieceTypeId
from chess_core.core.state import GameState

if TYPE_CHECKING:
    from chess_core.core.gamemode import GameMode


@dataclass(frozen=True, slots=True)
class LegalTurnOption:
    turn: Turn
    notation: str = ""
    source_square: int | None = None
    target_square: int | None = None
    reserve_piece: PieceTypeId | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class LegalTurnOptions:
    options: tuple[LegalTurnOption, ...]

    def by_source(self) -> dict[int | None, tuple[LegalTurnOption, ...]]:
        grouped: dict[int | None, list[LegalTurnOption]] = {}
        for option in self.options:
            grouped.setdefault(option.source_square, []).append(option)
        return {key: tuple(value) for key, value in grouped.items()}

    def by_target(self) -> dict[int | None, tuple[LegalTurnOption, ...]]:
        grouped: dict[int | None, list[LegalTurnOption]] = {}
        for option in self.options:
            grouped.setdefault(option.target_square, []).append(option)
        return {key: tuple(value) for key, value in grouped.items()}

    def by_reserve(self) -> dict[PieceTypeId | None, tuple[LegalTurnOption, ...]]:
        grouped: dict[PieceTypeId | None, list[LegalTurnOption]] = {}
        for option in self.options:
            grouped.setdefault(option.reserve_piece, []).append(option)
        return {key: tuple(value) for key, value in grouped.items()}


def build_legal_turn_options(
    mode: GameMode,
    state: GameState,
    turns: list[Turn],
    *,
    notation_style: NotationStyle = NotationStyle.FROM_TO,
) -> LegalTurnOptions:
    files = state.board_state.board.shape.files
    options: list[LegalTurnOption] = []
    for turn in turns:
        after = mode.apply_turn(state, turn, record_history=False)
        notation = mode.format_turn(
            turn, before=state, after=after, style=notation_style
        )
        source, target, reserve = _primary_indices(turn, files)
        options.append(
            LegalTurnOption(
                turn=turn,
                notation=notation,
                source_square=source,
                target_square=target,
                reserve_piece=reserve,
            )
        )
    return LegalTurnOptions(tuple(options))


def _primary_indices(
    turn: Turn, files: int
) -> tuple[int | None, int | None, PieceTypeId | None]:
    source: int | None = None
    target: int | None = None
    reserve: PieceTypeId | None = None
    for action in turn.actions:
        if isinstance(action, MoveAction):
            source = action.from_square.index(files)
            target = action.to_square.index(files)
        elif isinstance(action, (DropAction, PlaceAction)):
            reserve = action.piece_type
            target = action.to_square.index(files)
    return source, target, reserve
