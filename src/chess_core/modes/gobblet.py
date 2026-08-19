"""Gobblet Gobblers on a 3x3 board."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import PieceCatalog, PieceType
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.gobblet_rules import (
    GOBBLET_TYPES,
    GobbletOptions,
    GobbletRulesStrategy,
    initial_reserve,
)

GOBBLET_RELOCATE = "relocate"


def gobblet(options: GobbletOptions | None = None) -> GameMode:
    options = options or GobbletOptions()
    catalog = PieceCatalog()
    for piece_type in GOBBLET_TYPES:
        catalog.register(PieceType(piece_type, ()))
    return (
        GameModeBuilder(gobblet_mode_id(options), "Gobblet Gobblers")
        .with_shape(3, 3)
        .with_pieces(catalog)
        .with_turn_scenario(
            TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),))
        )
        .with_victory(VictoryCondition(VictoryKind.CUSTOM))
        .with_initial_extras(
            {
                "stacks": {},
                "reserve": initial_reserve(),
                "gobblet_options": options,
            }
        )
        .with_facing_opponent(True)
        .with_rules(GobbletRulesStrategy(options))
        .build()
    )


def resolve_gobblet_mode_id(mode_id: str) -> GameMode:
    parts = tuple(part for part in mode_id.split("+") if part)
    if not parts or parts[0] != "gobblet":
        raise KeyError(f"not a gobblet mode id: {mode_id}")
    if len(parts) == 1:
        return gobblet()
    if parts[1:] == (GOBBLET_RELOCATE,):
        return gobblet(GobbletOptions(allow_board_moves=True))
    raise ValueError(f"unknown gobblet modifier: {parts[1]}")


def gobblet_mode_id(options: GobbletOptions | None = None) -> str:
    options = options or GobbletOptions()
    if options.allow_board_moves:
        return f"gobblet+{GOBBLET_RELOCATE}"
    return "gobblet"
