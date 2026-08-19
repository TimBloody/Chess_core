"""8x8 Reversi / Othello (WOF)."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import Piece, PieceCatalog, PieceSide, PieceType
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.reversi_rules import DISC, ReversiRulesStrategy

# d4, e4, d5, e5 at files=8
_START_WHITE = (27, 36)
_START_BLACK = (28, 35)


def reversi() -> GameMode:
    return (
        GameModeBuilder("reversi", "Реверси")
        .with_shape(8, 8)
        .with_pieces(_piece_catalog())
        .with_turn_scenario(
            TurnScenario(
                (
                    TurnStep(StepKind.PLACE, optional=True),
                    TurnStep(StepKind.OPTIONAL_PASS, optional=True),
                )
            )
        )
        .with_victory(VictoryCondition(VictoryKind.CUSTOM))
        .with_start_cells(_start_cells())
        .with_initial_extras({"starting_side": PieceSide.BLACK})
        .with_rules(ReversiRulesStrategy())
        .build()
    )


def _piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(PieceType(DISC, ()))
    return catalog


def _start_cells() -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    for index in _START_WHITE:
        cells[index] = Piece(DISC, PieceSide.WHITE)
    for index in _START_BLACK:
        cells[index] = Piece(DISC, PieceSide.BLACK)
    return cells
