"""Map piece types to SVG keys without putting rules in widgets."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode
from chess_core.core.piece import Piece, PieceSide, PieceTypeId

FACING_ASSET_FAMILIES = frozenset({"shogi", "dobutsu"})

_CHESS = {
    "king": "K",
    "queen": "Q",
    "rook": "R",
    "bishop": "B",
    "knight": "N",
    "pawn": "P",
}

_SHOGI = {
    "king": "OU",
    "gold": "KI",
    "silver": "GI",
    "knight": "KE",
    "lance": "KY",
    "pawn": "FU",
    "bishop": "KA",
    "rook": "HI",
    "tokin": "TO",
    "promoted_lance": "NY",
    "promoted_knight": "NK",
    "promoted_silver": "NG",
    "horse": "UM",
    "dragon": "RY",
}

_DOBUTSU = {
    "lion": "lion",
    "giraffe": "giraffe",
    "elephant": "elephant",
    "chick": "chick",
    "hen": "hen",
}

_CHESS_HAND_ORDER = ("pawn", "knight", "bishop", "rook", "queen")
_SHOGI_HAND_ORDER = ("pawn", "lance", "knight", "silver", "gold", "bishop", "rook")
_DOBUTSU_HAND_ORDER = ("chick", "giraffe", "elephant", "hen")


def parse_display_key(piece_key: str) -> tuple[str, PieceSide | None]:
    """Split ``stem@b`` / ``stem@w`` owner tags used for 180° facing."""
    if "@" not in piece_key:
        return piece_key, None
    stem, owner = piece_key.rsplit("@", 1)
    if owner == "w":
        return stem, PieceSide.WHITE
    if owner == "b":
        return stem, PieceSide.BLACK
    return piece_key, None


def piece_asset_key(piece: Piece, asset_family: str = "chess") -> str | None:
    """Return a Lichess, Lishogi, or Dobutsu SVG stem for ``piece``."""
    name = piece.piece_type.name
    if asset_family == "dobutsu":
        code = _DOBUTSU.get(name)
        if code is None:
            return None
        owner = "b" if piece.side is PieceSide.BLACK else "w"
        return f"dobutsu/{code}@{owner}"
    if asset_family == "shogi":
        code = _SHOGI.get(name)
        if code is None:
            return None
        prefix = "0" if piece.side is PieceSide.WHITE else "1"
        return f"{prefix}{code}"
    symbol = _CHESS.get(name)
    if symbol is None:
        return None
    return ("w" if piece.side is PieceSide.WHITE else "b") + symbol


def droppable_type_names(mode: GameMode) -> tuple[str, ...]:
    """Capturable types a hand tray may show, in display order."""
    royal = mode.royal_type
    names = [
        piece_type.id.name
        for piece_type in mode.pieces.all_types()
        if piece_type.id.name != royal
    ]
    if mode.asset_family == "dobutsu":
        preferred = _DOBUTSU_HAND_ORDER
    elif mode.asset_family == "shogi":
        preferred = _SHOGI_HAND_ORDER
    else:
        preferred = _CHESS_HAND_ORDER
    seen = set(names)
    return tuple(
        [name for name in preferred if name in seen]
        + [name for name in names if name not in preferred]
    )


def hand_piece_key(type_name: str, side: PieceSide, asset_family: str) -> str | None:
    """SVG key for a pocket token of ``type_name`` belonging to ``side``."""
    return piece_asset_key(Piece(PieceTypeId(type_name), side), asset_family)
