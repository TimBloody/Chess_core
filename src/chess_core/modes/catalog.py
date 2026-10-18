"""Shared placeholder piece catalogs for built-in mode factories."""

from __future__ import annotations

from chess_core.core.piece import (
    MovePattern,
    MovePatternKind,
    PieceCatalog,
    PieceType,
    PieceTypeId,
)

ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
KING_STEPS = ORTHOGONAL + DIAGONAL
GOLD_STEPS = ((0, 1), (1, 1), (-1, 1), (1, 0), (-1, 0), (0, -1))
SILVER_STEPS = ((0, 1), (1, 1), (-1, 1), (1, -1), (-1, -1))
SHOGI_KNIGHT = ((1, 2), (-1, 2))
FORWARD = ((0, 1),)
KNIGHT_LEAPS = (
    (1, 2), (2, 1), (2, -1), (1, -2),
    (-1, -2), (-2, -1), (-2, 1), (-1, 2),
)


def chess_piece_catalog() -> PieceCatalog:
    """Standard chess types expressed as reusable movement patterns."""
    catalog = PieceCatalog()
    definitions = (
        PieceType(PieceTypeId("king"), (MovePattern(MovePatternKind.LEAP, KING_STEPS),)),
        PieceType(PieceTypeId("queen"), (MovePattern(MovePatternKind.SLIDE, KING_STEPS),)),
        PieceType(PieceTypeId("rook"), (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),)),
        PieceType(PieceTypeId("bishop"), (MovePattern(MovePatternKind.SLIDE, DIAGONAL),)),
        PieceType(PieceTypeId("knight"), (MovePattern(MovePatternKind.LEAP, KNIGHT_LEAPS),)),
        PieceType(
            PieceTypeId("pawn"),
            (MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="pawn"),),
            can_promote=True,
        ),
    )
    for definition in definitions:
        catalog.register(definition)
    return catalog


def kyoto_shogi_piece_catalog() -> PieceCatalog:
    """Kyoto shogi faces; flip behavior is configured by the mode."""
    catalog = PieceCatalog()
    forward_steps = ((0, 1),)
    definitions = (
        PieceType(PieceTypeId("king"), (MovePattern(MovePatternKind.LEAP, KING_STEPS),)),
        PieceType(PieceTypeId("tokin"), (MovePattern(MovePatternKind.LEAP, ((0, 1), (1, 1), (-1, 1), (1, 0), (-1, 0), (0, -1))),)),
        PieceType(PieceTypeId("lance"), (MovePattern(MovePatternKind.SLIDE, forward_steps),)),
        PieceType(PieceTypeId("silver"), (MovePattern(MovePatternKind.LEAP, ((0, 1), (1, 1), (-1, 1), (1, -1), (-1, -1))),)),
        PieceType(PieceTypeId("bishop"), (MovePattern(MovePatternKind.SLIDE, DIAGONAL),)),
        PieceType(PieceTypeId("gold"), (MovePattern(MovePatternKind.LEAP, ((0, 1), (1, 1), (-1, 1), (1, 0), (-1, 0), (0, -1))),)),
        PieceType(PieceTypeId("knight"), (MovePattern(MovePatternKind.LEAP, ((1, 2), (-1, 2))),)),
        PieceType(PieceTypeId("pawn"), (MovePattern(MovePatternKind.LEAP, forward_steps),)),
        PieceType(PieceTypeId("rook"), (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),)),
    )
    for definition in definitions:
        catalog.register(definition)
    return catalog


def shogi_piece_catalog() -> PieceCatalog:
    """Standard 9x9 shogi types including promoted faces."""
    gold = (MovePattern(MovePatternKind.LEAP, GOLD_STEPS),)
    catalog = PieceCatalog()
    definitions = (
        PieceType(PieceTypeId("king"), (MovePattern(MovePatternKind.LEAP, KING_STEPS),)),
        PieceType(PieceTypeId("gold"), gold),
        PieceType(PieceTypeId("silver"), (MovePattern(MovePatternKind.LEAP, SILVER_STEPS),), can_promote=True),
        PieceType(PieceTypeId("knight"), (MovePattern(MovePatternKind.LEAP, SHOGI_KNIGHT),), can_promote=True),
        PieceType(PieceTypeId("lance"), (MovePattern(MovePatternKind.SLIDE, FORWARD),), can_promote=True),
        PieceType(PieceTypeId("pawn"), (MovePattern(MovePatternKind.LEAP, FORWARD),), can_promote=True),
        PieceType(PieceTypeId("bishop"), (MovePattern(MovePatternKind.SLIDE, DIAGONAL),), can_promote=True),
        PieceType(PieceTypeId("rook"), (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),), can_promote=True),
        PieceType(PieceTypeId("tokin"), gold),
        PieceType(PieceTypeId("promoted_lance"), gold),
        PieceType(PieceTypeId("promoted_knight"), gold),
        PieceType(PieceTypeId("promoted_silver"), gold),
        PieceType(
            PieceTypeId("horse"),
            (
                MovePattern(MovePatternKind.SLIDE, DIAGONAL),
                MovePattern(MovePatternKind.LEAP, KING_STEPS),
            ),
        ),
        PieceType(
            PieceTypeId("dragon"),
            (
                MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),
                MovePattern(MovePatternKind.LEAP, KING_STEPS),
            ),
        ),
    )
    for definition in definitions:
        catalog.register(definition)
    return catalog


def dobutsu_shogi_piece_catalog() -> PieceCatalog:
    """Dobutsu shogi animals with leap patterns."""
    catalog = PieceCatalog()
    definitions = (
        PieceType(PieceTypeId("lion"), (MovePattern(MovePatternKind.LEAP, KING_STEPS),)),
        PieceType(PieceTypeId("giraffe"), (MovePattern(MovePatternKind.LEAP, ORTHOGONAL),)),
        PieceType(PieceTypeId("elephant"), (MovePattern(MovePatternKind.LEAP, DIAGONAL),)),
        PieceType(PieceTypeId("chick"), (MovePattern(MovePatternKind.LEAP, FORWARD),), can_promote=True),
        PieceType(PieceTypeId("hen"), (MovePattern(MovePatternKind.LEAP, GOLD_STEPS),)),
    )
    for definition in definitions:
        catalog.register(definition)
    return catalog


def reversi_piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(
        PieceType(PieceTypeId("disc"), (MovePattern(MovePatternKind.LEAP, ()),), captures_on_landing=False)
    )
    return catalog


def corners_piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(
        PieceType(
            PieceTypeId("man"),
            (MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="corners_man"),),
            captures_on_landing=False,
        )
    )
    return catalog


def draughts_piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    catalog.register(
        PieceType(
            PieceTypeId("man"),
            (
                MovePattern(MovePatternKind.LEAP, ((1, 1), (-1, 1))),
                MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="draughts_man_jump"),
            ),
            can_promote=True,
            captures_on_landing=False,
        )
    )
    catalog.register(
        PieceType(
            PieceTypeId("kingman"),
            (
                MovePattern(MovePatternKind.SLIDE, DIAGONAL),
                MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="draughts_king_jump"),
            ),
            captures_on_landing=False,
        )
    )
    return catalog


def gobblet_piece_catalog() -> PieceCatalog:
    catalog = PieceCatalog()
    for name in ("gobblet_small", "gobblet_medium", "gobblet_large"):
        catalog.register(
            PieceType(
                PieceTypeId(name),
                (MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="cover_any"),),
                captures_on_landing=False,
            )
        )
    return catalog
