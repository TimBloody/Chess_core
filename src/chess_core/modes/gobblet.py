"""Gobblet Gobblers on a 3×3 board."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import gobblet_piece_catalog
from chess_core.modes.gobblet_rules import ALIGN_LINES, GOBBLET_SIZES, GobbletDropRule, GobbletHailMary


def gobblet() -> GameMode:
    """Place from reserve or move a visible gobbler; larger covers smaller."""
    return (
        GameModeBuilder("gobblet", "Gobblet Gobblers")
        .with_shape(3, 3)
        .with_pieces(gobblet_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),)))
        .with_victory(VictoryCondition(VictoryKind.ALIGN, lose_on_no_legal_moves=False))
        .with_drop_rule(GobbletDropRule())
        .with_legality(GobbletHailMary())
        .with_checks_enabled(False)
        .with_royal_type("")
        .with_initial_extras(
            {
                "stacks": {},
                "stack_covers": True,
                "cover_sizes": dict(GOBBLET_SIZES),
                "align_lines": ALIGN_LINES,
                "hand_stock": {
                    "gobblet_small": 2,
                    "gobblet_medium": 2,
                    "gobblet_large": 2,
                },
                "eval_search_depth": 3,
            }
        )
        .build()
    )
