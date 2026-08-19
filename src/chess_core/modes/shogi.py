"""Shogi and shogi-variant mode factories."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.catalog import (
    dobutsu_shogi_piece_catalog,
    kyoto_shogi_piece_catalog,
    minishogi_piece_catalog,
    shogi_piece_catalog,
)
from chess_core.modes.shogi_rules import (
    DOBUTSU_PROMOTIONS,
    STANDARD_SHOGI_PROMOTIONS,
    KyotoDropRule,
    KyotoFlipTransform,
    ShogiDropRule,
    ShogiPromotionRule,
    facing_start_cells,
)


def shogi() -> GameMode:
    """9x9 standard shogi: drops, 3-rank promotion, checkmate."""
    return (
        _shogi_builder("shogi", "Shogi", 9, 9, shogi_piece_catalog())
        .with_drop_rule(ShogiDropRule())
        .with_promotion_rule(
            ShogiPromotionRule(zone_depth=3, mapping=STANDARD_SHOGI_PROMOTIONS)
        )
        .with_start_cells(_shogi_start_cells())
        .build()
    )


def minishogi() -> GameMode:
    """5x5 minishogi: one-rank promotion zone, otherwise standard drops."""
    return (
        _shogi_builder("minishogi", "Minishogi", 5, 5, minishogi_piece_catalog())
        .with_drop_rule(ShogiDropRule())
        .with_promotion_rule(
            ShogiPromotionRule(zone_depth=1, mapping=STANDARD_SHOGI_PROMOTIONS)
        )
        .with_start_cells(_minishogi_start_cells())
        .build()
    )


def kyoto_shogi() -> GameMode:
    """
    5x5 Kyoto shogi (Tamiya Katsuya).

    - No promotion zone: every non-king piece flips to its paired type after each move.
    - Pairs: Tokin<->Lance, Silver<->Bishop, Gold<->Knight, Pawn<->Rook; King does not flip.
    - Drops: captured piece may be placed with either face up (DropRule.allowed_faces).
    - Relaxed drop restrictions vs standard shogi (same file pawn, last rank, etc.).
    - Victory: checkmate (same goal as shogi).
    """
    catalog = kyoto_shogi_piece_catalog()
    flip = KyotoFlipTransform()
    for piece_type in catalog.all_types():
        if not piece_type.is_royal:
            piece_type.transforms_on_move = flip

    return (
        _shogi_builder("kyoto_shogi", "Kyoto Shogi", 5, 5, catalog)
        .with_drop_rule(KyotoDropRule())
        .with_start_cells(
            facing_start_cells(5, 5, {0: ("tokin", "silver", "king", "gold", "pawn")})
        )
        .build()
    )


def dobutsu_shogi() -> GameMode:
    """3x4 animal shogi: capture the lion or a safe try on the last rank."""
    return (
        _shogi_builder(
            "dobutsu_shogi",
            "Dobutsu Shogi",
            3,
            4,
            dobutsu_shogi_piece_catalog(),
        )
        .with_drop_rule(
            ShogiDropRule(nifu=False, dead_squares=False, forbid_pawn_drop_mate=False)
        )
        .with_promotion_rule(
            ShogiPromotionRule(zone_depth=1, mapping=DOBUTSU_PROMOTIONS)
        )
        .with_victory(
            (
                VictoryCondition(VictoryKind.KING_CAPTURE),
                VictoryCondition(VictoryKind.KING_REACHES_ZONE),
            )
        )
        .with_start_cells(_dobutsu_start_cells())
        .with_asset_family("dobutsu")
        .build()
    )


def _shogi_builder(mode_id: str, name: str, files: int, ranks: int, catalog) -> GameModeBuilder:
    builder = (
        GameModeBuilder(mode_id, name)
        .with_shape(files, ranks)
        .with_pieces(catalog)
        .with_turn_scenario(TurnScenario((TurnStep(StepKind.MOVE_OR_DROP),)))
        .with_victory(VictoryCondition(VictoryKind.CHECKMATE))
        .with_shogi_presentation()
    )
    return builder


def _shogi_start_cells() -> dict:
    empty = (None,)
    return facing_start_cells(
        9,
        9,
        {
            0: ("lance", "knight", "silver", "gold", "king", "gold", "silver", "knight", "lance"),
            1: empty + ("bishop",) + empty * 5 + ("rook",) + empty,
            2: ("pawn",) * 9,
        },
    )


def _minishogi_start_cells() -> dict:
    return facing_start_cells(
        5,
        5,
        {
            0: ("king", "gold", "silver", "bishop", "rook"),
            1: ("pawn", None, None, None, None),
        },
    )


def _dobutsu_start_cells() -> dict:
    return facing_start_cells(
        3,
        4,
        {
            0: ("elephant", "lion", "giraffe"),
            1: (None, "chick", None),
        },
    )
