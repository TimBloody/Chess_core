"""Bughouse: two crazyhouse boards with partner capture routing."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode
from chess_core.core.rules import CaptureSink
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.chess import _chess_mode
from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule


def bughouse() -> GameMode:
    """One-board ruleset used twice by the match layer."""
    return _chess_mode(
        "bughouse",
        "Bughouse",
        scenario=TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),)),
        drop_rule=CrazyhouseDropRule(),
        capture_sink=CaptureSink.PARTNER_OUTBOUND,
        extras={"match_kind": "bughouse", "board_count": 2},
    )
