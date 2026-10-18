"""6x6 Hasami shogi mode factory."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import (
    MovePattern,
    MovePatternKind,
    Piece,
    PieceCatalog,
    PieceSide,
    PieceType,
    PieceTypeId,
)
from chess_core.core.rules import CaptureSink, VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import ORTHOGONAL
from chess_core.modes.line_capture_common import LineCaptureTransition

BOARD_FILES = 6
BOARD_RANKS = 6
PAWN = PieceTypeId("pawn")


def hasami_shogi() -> GameMode:
    return (
        GameModeBuilder("hasami_shogi", "Хасами сёги")
        .with_shape(BOARD_FILES, BOARD_RANKS)
        .with_pieces(_piece_catalog())
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),)))
        .with_victory(VictoryCondition(VictoryKind.MATERIAL, lose_on_no_legal_moves=False))
        .with_capture_sink(CaptureSink.DESTROY)
        .with_start_cells(_start_cells())
        .with_checks_enabled(False)
        .with_royal_type("")
        .with_asset_family("shogi")
        .with_transitions((LineCaptureTransition("hasami"),))
        .with_initial_extras(
            {
                "empty_side_wins": False,
                "blocked_side_wins": False,
                "material_win_threshold": 1,
                "line_capture": "hasami",
                "starting_side": "BLACK",
            }
        )
        .build()
    )


def _piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(
        PieceType(
            PAWN,
            (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),),
            captures_on_landing=False,
        )
    )
    return catalog


def _start_cells() -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    for file in range(BOARD_FILES):
        cells[file] = Piece(PAWN, PieceSide.WHITE)
        cells[(BOARD_RANKS - 1) * BOARD_FILES + file] = Piece(PAWN, PieceSide.BLACK)
    return cells
