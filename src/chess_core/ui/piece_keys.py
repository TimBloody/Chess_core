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

_BOARDGAME_STEMS = {
    "disc": "disc",
    "man": "disc",
    "kingman": "kingman",
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
_GOBBLET_HAND_ORDER = ("gobblet_small", "gobblet_medium", "gobblet_large")


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


def should_rotate_facing_art(piece_key: str, *, facing_black: bool) -> bool:
    """Whether the SVG must be painter-rotated 180° for the current seat.

    ``stem@w`` / ``stem@b`` (dobutsu) store upright art: rotate the side that
    currently sits on the far rank so wedges point toward the opponent.

    Lishogi ``0XX`` / ``1XX`` files already face sente-up / gote-down. They
    need an extra 180° only after the board is flipped, so the near komadai
    still looks like the viewer's own pieces.
    """
    stem, tagged = parse_display_key(piece_key)
    if tagged is not None:
        far_side = PieceSide.WHITE if facing_black else PieceSide.BLACK
        return tagged is far_side
    if _baked_shogi_facing(stem):
        return facing_black
    return False


def _baked_shogi_facing(stem: str) -> bool:
    return len(stem) >= 3 and stem[0] in {"0", "1"} and stem[1].isalpha()


def piece_asset_key(piece: Piece, asset_family: str = "chess") -> str | None:
    """Return a Lichess, Lishogi, Dobutsu, or board-game SVG stem for ``piece``."""
    name = piece.piece_type.name
    if piece.side is PieceSide.NEUTRAL or name == "blocker":
        return "blocker"
    if name in _BOARDGAME_STEMS or name.startswith("gobblet_"):
        prefix = "w" if piece.side is PieceSide.WHITE else "b"
        return prefix + _BOARDGAME_STEMS.get(name, name)
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
    elif any(name.startswith("gobblet_") for name in names):
        preferred = _GOBBLET_HAND_ORDER
    else:
        preferred = _CHESS_HAND_ORDER
    seen = set(names)
    return tuple(
        [name for name in preferred if name in seen]
        + [name for name in names if name not in preferred]
    )


def drop_flip_map(mode: GameMode) -> dict[str, str]:
    """Kyoto-style hand faces: each capturable type maps to its opposite side."""
    rule = mode.drop_rule
    if rule is None:
        return {}
    mapping: dict[str, str] = {}
    for piece_type in mode.pieces.all_types():
        faces = rule.allowed_faces(piece_type.id)
        if faces is None or len(faces) < 2:
            continue
        mapping[faces[0]] = faces[1]
        mapping[faces[1]] = faces[0]
    return mapping


def hand_piece_key(type_name: str, side: PieceSide, asset_family: str) -> str | None:
    """SVG key for a pocket token of ``type_name`` belonging to ``side``."""
    return piece_asset_key(Piece(PieceTypeId(type_name), side), asset_family)
