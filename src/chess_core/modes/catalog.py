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
    """Standard shogi piece names without move generation patterns yet."""
    return _catalog_with_names(
        (
            "king",
            "rook",
            "bishop",
            "gold",
            "silver",
            "knight",
            "lance",
            "pawn",
        )
    )


def dobutsu_shogi_piece_catalog() -> PieceCatalog:
    """Dobutsu shogi piece names without move generation patterns yet."""
    return _catalog_with_names(("lion", "giraffe", "elephant", "chick", "hen"))


def _catalog_with_names(names: tuple[str, ...]) -> PieceCatalog:
    catalog = PieceCatalog()
    for name in names:
        catalog.register(PieceType(id=PieceTypeId(name), patterns=()))
    return catalog
