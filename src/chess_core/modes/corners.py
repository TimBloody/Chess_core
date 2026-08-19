"""Configurable 8x8 Corners (Уголки) mode."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import Piece, PieceCatalog, PieceSide, PieceType
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.corners_rules import (
    CORNER,
    CornersMoveProvider,
    CornersRulesStrategy,
    layout_homes,
)


CORNER_LAYOUTS = ("3x3", "3x4", "1234")


def corners(layout: str = "3x4") -> GameMode:
    if layout not in CORNER_LAYOUTS:
        raise ValueError(f"unknown corners layout: {layout}")
    white_home, black_home = layout_homes(layout)
    return (
        GameModeBuilder(corners_mode_id(layout), "Уголки")
        .with_shape(8, 8)
        .with_pieces(_piece_catalog())
        .with_move_provider(CornersMoveProvider())
        .with_turn_scenario(
            TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),))
        )
        .with_victory(VictoryCondition(VictoryKind.CUSTOM))
        .with_start_cells(_start_cells(white_home, black_home))
        .with_initial_extras(
            {
                "white_home": white_home,
                "black_home": black_home,
                "corners_layout": layout,
            }
        )
        .with_rules(CornersRulesStrategy())
        .build()
    )


def resolve_corners_mode_id(mode_id: str) -> GameMode:
    parts = tuple(part for part in mode_id.split("+") if part)
    if not parts or parts[0] != "corners":
        raise KeyError(f"not a corners mode id: {mode_id}")
    if len(parts) == 1:
        return corners()
    if len(parts) == 2:
        layout = parts[1]
        if layout not in CORNER_LAYOUTS:
            raise ValueError(f"unknown corners layout: {layout}")
        return corners(layout)
    raise ValueError(f"invalid corners mode id: {mode_id}")


def corners_mode_id(layout: str = "3x4") -> str:
    if layout not in CORNER_LAYOUTS:
        raise ValueError(f"unknown corners layout: {layout}")
    if layout == "3x4":
        return "corners"
    return "+".join(("corners", layout))


def _piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(PieceType(CORNER, ()))
    return catalog


def _start_cells(
    white_home: frozenset[int], black_home: frozenset[int]
) -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    for index in white_home:
        cells[index] = Piece(CORNER, PieceSide.WHITE)
    for index in black_home:
        cells[index] = Piece(CORNER, PieceSide.BLACK)
    return cells
