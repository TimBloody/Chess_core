"""Freestyle Gomoku on a 15x15 board."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import PieceCatalog, PieceSide, PieceType
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.gomoku_rules import GomokuRulesStrategy, STONE


def gomoku() -> GameMode:
    catalog = PieceCatalog()
    catalog.register(PieceType(STONE, ()))
    return (
        GameModeBuilder("gomoku", "Гомоку")
        .with_shape(15, 15)
        .with_pieces(catalog)
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.PLACE),)))
        .with_victory(VictoryCondition(VictoryKind.CUSTOM))
        .with_initial_extras({"starting_side": PieceSide.BLACK})
        .with_rules(GomokuRulesStrategy())
        .build()
    )
