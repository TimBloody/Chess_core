"""Map logical pieces to SVG asset keys for the current game mode."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode
from chess_core.core.piece import Piece, PieceSide, PieceTypeId

_CHESS_FALLBACK = {
    "king": "K",
    "queen": "Q",
    "rook": "R",
    "bishop": "B",
    "knight": "N",
    "pawn": "P",
}

_CHESS_HAND_ORDER = ("pawn", "knight", "bishop", "rook", "queen", "king")

_SHOGI_HAND_ORDER = (
    "pawn",
    "lance",
    "knight",
    "silver",
    "gold",
    "bishop",
    "rook",
    "king",
    "chick",
    "giraffe",
    "elephant",
    "lion",
    "tokin",
    "hen",
)

_GOBBLET_HAND_ORDER = ("gobblet_small", "gobblet_medium", "gobblet_large")

FACING_ASSET_FAMILIES = frozenset({"shogi", "dobutsu"})


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


def piece_svg_key(mode: GameMode | Piece, piece: Piece | None = None) -> str:
    """Return the SVG stem used by AssetsLoader for this piece."""
    if piece is None:
        if not isinstance(mode, Piece):
            raise TypeError("piece_svg_key(piece) requires a Piece")
        piece = mode
        if piece.side is PieceSide.NEUTRAL:
            return "duck"
        prefix = "w" if piece.side is PieceSide.WHITE else "b"
        return prefix + piece.piece_type.name
    if piece.side is PieceSide.NEUTRAL:
        return "duck"
    return piece_svg_key_for(mode, piece.piece_type.name, piece.side)


def piece_svg_key_for(mode: GameMode, type_name: str, side: PieceSide) -> str:
    definition = None
    try:
        definition = mode.pieces.get(PieceTypeId(type_name))
    except KeyError:
        pass
    asset_key = definition.asset_key if definition is not None else None
    if mode.asset_family in FACING_ASSET_FAMILIES:
        code = asset_key or type_name[:2].upper()
        stem = f"0{code}"
        if mode.asset_family == "dobutsu":
            stem = f"dobutsu/{stem}"
        owner = "b" if side is PieceSide.BLACK else "w"
        return f"{stem}@{owner}"
    symbol = asset_key or _CHESS_FALLBACK.get(type_name, type_name)
    return ("w" if side is PieceSide.WHITE else "b") + symbol


def shogi_hand_order() -> tuple[str, ...]:
    return _SHOGI_HAND_ORDER


def chess_hand_order() -> tuple[str, ...]:
    return _CHESS_HAND_ORDER


def hand_slot_types(mode: GameMode) -> tuple[str, ...]:
    """Piece types a hand tray must reserve a token for.

    Counts Kyoto dual faces as separate slots so the tray is wide/tall
    enough even when every capturable type is in hand.
    """
    drop_rule = mode.drop_rule
    seen: set[str] = set()
    collected: list[str] = []

    def add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            collected.append(name)

    for piece_type in mode.pieces.all_types():
        if piece_type.is_royal:
            continue
        base = piece_type.demotes_to or piece_type.id.name
        faces = drop_rule.allowed_faces(PieceTypeId(base)) if drop_rule is not None else None
        if faces:
            for face in faces:
                add(face)
        else:
            add(base)

    if any(name in _GOBBLET_HAND_ORDER for name in seen):
        preferred = _GOBBLET_HAND_ORDER
    elif mode.asset_family in FACING_ASSET_FAMILIES:
        preferred = _SHOGI_HAND_ORDER
    else:
        preferred = _CHESS_HAND_ORDER
    return tuple([name for name in preferred if name in seen] + [name for name in collected if name not in preferred])
