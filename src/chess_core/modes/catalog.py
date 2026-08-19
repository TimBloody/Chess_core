"""Shared piece catalogs for built-in mode factories."""

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
FORWARD = ((0, 1),)
GOLD_STEPS = ((0, 1), (1, 1), (-1, 1), (1, 0), (-1, 0), (0, -1))
SILVER_STEPS = ((0, 1), (1, 1), (-1, 1), (1, -1), (-1, -1))
SHOGI_KNIGHT_STEPS = ((1, 2), (-1, 2))


def chess_piece_catalog() -> PieceCatalog:
    """Standard chess types expressed as reusable movement patterns."""
    catalog = PieceCatalog()
    definitions = (
        PieceType(
            PieceTypeId("king"),
            (MovePattern(MovePatternKind.LEAP, KING_STEPS),),
            is_royal=True,
            asset_key="K",
        ),
        PieceType(
            PieceTypeId("queen"),
            (MovePattern(MovePatternKind.SLIDE, KING_STEPS),),
            asset_key="Q",
        ),
        PieceType(
            PieceTypeId("rook"),
            (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),),
            asset_key="R",
        ),
        PieceType(
            PieceTypeId("bishop"),
            (MovePattern(MovePatternKind.SLIDE, DIAGONAL),),
            asset_key="B",
        ),
        PieceType(
            PieceTypeId("knight"),
            (MovePattern(MovePatternKind.LEAP, KNIGHT_LEAPS),),
            asset_key="N",
        ),
        PieceType(
            PieceTypeId("pawn"),
            (MovePattern(MovePatternKind.CUSTOM_MASK, pattern_key="pawn"),),
            can_promote=True,
            asset_key="P",
        ),
    )
    for definition in definitions:
        catalog.register(definition)
    return catalog


def kyoto_shogi_piece_catalog() -> PieceCatalog:
    """Kyoto shogi faces; flip behavior is configured by the mode."""
    catalog = PieceCatalog()
    for definition in (
        _royal_king(),
        _gold("tokin", asset_key="TO", sfen_symbol="+p"),
        _lance(),
        _silver(),
        _bishop(),
        _gold("gold", asset_key="KI", sfen_symbol="g"),
        _shogi_knight(),
        _pawn(),
        _rook(),
    ):
        catalog.register(definition)
    return catalog


def shogi_piece_catalog() -> PieceCatalog:
    """Standard 9x9 and minishogi types, including promoted forms."""
    catalog = PieceCatalog()
    for definition in (
        *_unpromoted_shogi_types(),
        _gold("tokin", asset_key="TO", demotes_to="pawn", sfen_symbol="+p"),
        _gold(
            "promoted_lance",
            asset_key="NY",
            demotes_to="lance",
            sfen_symbol="+l",
        ),
        _gold(
            "promoted_knight",
            asset_key="NK",
            demotes_to="knight",
            sfen_symbol="+n",
        ),
        _gold(
            "promoted_silver",
            asset_key="NG",
            demotes_to="silver",
            sfen_symbol="+s",
        ),
        _horse(),
        _dragon(),
    ):
        catalog.register(definition)
    return catalog


def minishogi_piece_catalog() -> PieceCatalog:
    """Minishogi uses the standard shogi set without lance or knight."""
    catalog = PieceCatalog()
    skip = {"lance", "knight", "promoted_lance", "promoted_knight"}
    for definition in shogi_piece_catalog().all_types():
        if definition.id.name not in skip:
            catalog.register(definition)
    return catalog


def dobutsu_shogi_piece_catalog() -> PieceCatalog:
    """Animal shogi: one-step giraffe/elephant, chick→hen, lion is royal."""
    catalog = PieceCatalog()
    for definition in (
        PieceType(
            PieceTypeId("lion"),
            (MovePattern(MovePatternKind.LEAP, KING_STEPS),),
            is_royal=True,
            asset_key="OU",
            sfen_symbol="k",
        ),
        PieceType(
            PieceTypeId("giraffe"),
            (MovePattern(MovePatternKind.LEAP, ORTHOGONAL),),
            asset_key="HI",
            sfen_symbol="r",
        ),
        PieceType(
            PieceTypeId("elephant"),
            (MovePattern(MovePatternKind.LEAP, DIAGONAL),),
            asset_key="KA",
            sfen_symbol="b",
        ),
        PieceType(
            PieceTypeId("chick"),
            (MovePattern(MovePatternKind.LEAP, FORWARD),),
            can_promote=True,
            asset_key="FU",
            sfen_symbol="p",
        ),
        _gold("hen", asset_key="TO", demotes_to="chick", sfen_symbol="+p"),
    ):
        catalog.register(definition)
    return catalog


def _unpromoted_shogi_types() -> tuple[PieceType, ...]:
    return (
        _royal_king(),
        _rook(can_promote=True),
        _bishop(can_promote=True),
        _gold("gold", asset_key="KI", sfen_symbol="g"),
        _silver(can_promote=True),
        _shogi_knight(can_promote=True),
        _lance(can_promote=True),
        _pawn(can_promote=True),
    )


def _royal_king() -> PieceType:
    return PieceType(
        PieceTypeId("king"),
        (MovePattern(MovePatternKind.LEAP, KING_STEPS),),
        is_royal=True,
        asset_key="OU",
        sfen_symbol="k",
    )


def _gold(
    name: str,
    *,
    asset_key: str,
    demotes_to: str | None = None,
    sfen_symbol: str | None = None,
) -> PieceType:
    return PieceType(
        PieceTypeId(name),
        (MovePattern(MovePatternKind.LEAP, GOLD_STEPS),),
        asset_key=asset_key,
        demotes_to=demotes_to,
        sfen_symbol=sfen_symbol,
    )


def _silver(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("silver"),
        (MovePattern(MovePatternKind.LEAP, SILVER_STEPS),),
        can_promote=can_promote,
        asset_key="GI",
        sfen_symbol="s",
    )


def _shogi_knight(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("knight"),
        (MovePattern(MovePatternKind.LEAP, SHOGI_KNIGHT_STEPS),),
        can_promote=can_promote,
        asset_key="KE",
        sfen_symbol="n",
    )


def _lance(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("lance"),
        (MovePattern(MovePatternKind.SLIDE, FORWARD),),
        can_promote=can_promote,
        asset_key="KY",
        sfen_symbol="l",
    )


def _pawn(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("pawn"),
        (MovePattern(MovePatternKind.LEAP, FORWARD),),
        can_promote=can_promote,
        asset_key="FU",
        sfen_symbol="p",
    )


def _bishop(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("bishop"),
        (MovePattern(MovePatternKind.SLIDE, DIAGONAL),),
        can_promote=can_promote,
        asset_key="KA",
        sfen_symbol="b",
    )


def _rook(*, can_promote: bool = False) -> PieceType:
    return PieceType(
        PieceTypeId("rook"),
        (MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),),
        can_promote=can_promote,
        asset_key="HI",
        sfen_symbol="r",
    )


def _horse() -> PieceType:
    return PieceType(
        PieceTypeId("horse"),
        (
            MovePattern(MovePatternKind.SLIDE, DIAGONAL),
            MovePattern(MovePatternKind.LEAP, ORTHOGONAL),
        ),
        asset_key="UM",
        demotes_to="bishop",
        sfen_symbol="+b",
    )


def _dragon() -> PieceType:
    return PieceType(
        PieceTypeId("dragon"),
        (
            MovePattern(MovePatternKind.SLIDE, ORTHOGONAL),
            MovePattern(MovePatternKind.LEAP, DIAGONAL),
        ),
        asset_key="RY",
        demotes_to="rook",
        sfen_symbol="+r",
    )
