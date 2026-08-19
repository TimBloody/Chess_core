"""Configurable 8x8 checkers mode."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.piece import Piece, PieceCatalog, PieceSide, PieceType
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.checkers_rules import (
    KING,
    MAN,
    CheckersMoveProvider,
    CheckersOptions,
)


CHECKERS_MODIFIERS = (
    "mandatory_capture",
    "backward_capture",
    "flying_king",
)


def checkers(options: CheckersOptions | None = None) -> GameMode:
    options = options or CheckersOptions()
    return (
        GameModeBuilder(checkers_mode_id(options), "Шашки")
        .with_shape(8, 8)
        .with_pieces(_piece_catalog())
        .with_move_provider(CheckersMoveProvider(options))
        .with_turn_scenario(
            TurnScenario((TurnStep(StepKind.MOVE_OR_CAPTURE),))
        )
        .with_victory(VictoryCondition(VictoryKind.MATERIAL))
        .with_start_cells(_start_cells())
        .with_initial_extras({"checkers_options": options})
        .build()
    )


def compose_checkers_mode(modifiers: tuple[str, ...]) -> GameMode:
    if "none" in modifiers:
        raise ValueError("unknown checkers modifier: none")
    unknown = set(modifiers) - set(CHECKERS_MODIFIERS)
    if unknown:
        raise ValueError(f"unknown checkers modifier: {sorted(unknown)[0]}")
    selected = set(modifiers)
    return checkers(
        CheckersOptions(
            mandatory_capture="mandatory_capture" in selected,
            backward_capture="backward_capture" in selected,
            flying_king="flying_king" in selected,
        )
    )


def resolve_checkers_mode_id(mode_id: str) -> GameMode:
    parts = tuple(part for part in mode_id.split("+") if part)
    if not parts or parts[0] != "checkers":
        raise KeyError(f"not a checkers mode id: {mode_id}")
    if len(parts) == 1:
        return checkers()
    if parts[1:] == ("none",):
        return checkers(
            CheckersOptions(
                mandatory_capture=False,
                backward_capture=False,
                flying_king=False,
            )
        )
    return compose_checkers_mode(parts[1:])


def checkers_mode_id(options: CheckersOptions) -> str:
    enabled = [
        name
        for name, value in (
            ("mandatory_capture", options.mandatory_capture),
            ("backward_capture", options.backward_capture),
            ("flying_king", options.flying_king),
        )
        if value
    ]
    if not enabled:
        return "checkers+none"
    if len(enabled) == len(CHECKERS_MODIFIERS):
        return "checkers"
    return "+".join(("checkers", *enabled))


def _piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(PieceType(MAN, (), can_promote=True))
    catalog.register(PieceType(KING, ()))
    return catalog


def _start_cells() -> dict[int, Piece]:
    cells: dict[int, Piece] = {}
    for rank in range(3):
        for file in range(8):
            if (file + rank) % 2 == 0:
                cells[rank * 8 + file] = Piece(MAN, PieceSide.WHITE)
    for rank in range(5, 8):
        for file in range(8):
            if (file + rank) % 2 == 0:
                cells[rank * 8 + file] = Piece(MAN, PieceSide.BLACK)
    return cells
