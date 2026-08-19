"""SFEN import/export for shogi-like rectangular positions."""

from __future__ import annotations

from collections import Counter

from chess_core.core.gamemode import GameMode
from chess_core.core.notation import encode_board_placement
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState, HandsState

_SFEN_TO_TYPE = {
    "k": "king",
    "r": "rook",
    "b": "bishop",
    "g": "gold",
    "s": "silver",
    "n": "knight",
    "l": "lance",
    "p": "pawn",
    "+p": "tokin",
    "+l": "promoted_lance",
    "+n": "promoted_knight",
    "+s": "promoted_silver",
    "+b": "horse",
    "+r": "dragon",
}

_HAND_ORDER = ("r", "b", "g", "s", "n", "l", "p")


def looks_like_sfen(text: str) -> bool:
    fields = text.strip().split()
    if len(fields) not in {3, 4}:
        return False
    return fields[1] in {"b", "w"} and "/" in fields[0]


def parse_sfen(sfen: str, mode: GameMode) -> GameState:
    fields = sfen.strip().split()
    if len(fields) not in {3, 4}:
        raise ValueError("SFEN must contain board, side, hands and optional move number")
    rows = fields[0].split("/")
    shape = mode.board.shape
    if len(rows) != shape.ranks:
        raise ValueError("SFEN rank count does not match board")
    to_type = _decode_map(mode)
    cells: dict[int, Piece | None] = {index: None for index in range(shape.cell_count)}
    for sfen_row, token in enumerate(rows):
        rank = shape.ranks - 1 - sfen_row
        file = 0
        index = 0
        while index < len(token):
            char = token[index]
            if char.isdigit():
                digits = char
                index += 1
                while index < len(token) and token[index].isdigit():
                    digits += token[index]
                    index += 1
                file += int(digits)
                continue
            promoted = char == "+"
            if promoted:
                index += 1
                if index >= len(token):
                    raise ValueError("SFEN promotion marker without a piece")
                char = token[index]
            key = f"+{char.lower()}" if promoted else char.lower()
            name = to_type.get(key)
            if name is None:
                raise ValueError(f"unsupported SFEN piece: {key!r}")
            if file >= shape.files:
                raise ValueError("SFEN rank exceeds board width")
            side = PieceSide.WHITE if char.isupper() else PieceSide.BLACK
            cells[rank * shape.files + file] = Piece(PieceTypeId(name), side)
            file += 1
            index += 1
        if file != shape.files:
            raise ValueError("SFEN rank width does not match board")
    if fields[1] not in {"b", "w"}:
        raise ValueError("invalid SFEN side to move")
    side = PieceSide.BLACK if fields[1] == "b" else PieceSide.WHITE
    extras: dict[str, object] = {"mode": mode}
    if len(fields) == 4:
        extras["fullmove_number"] = int(fields[3])
    hands = _parse_hands(fields[2], to_type)
    return GameState(BoardState(mode.board, cells), side, hands=hands, extras=extras)


def to_sfen(state: GameState) -> str:
    mode = state.extras.get("mode")
    to_symbol = _encode_map(mode)

    def token(piece: Piece) -> str | None:
        if piece.side is PieceSide.NEUTRAL:
            return None
        return _piece_sfen(piece, to_symbol)

    placement = encode_board_placement(state, token)
    active = "b" if state.side_to_move is PieceSide.BLACK else "w"
    hands = _hands_sfen(state.hands, to_symbol)
    move_number = state.extras.get("fullmove_number", 1)
    return f"{placement} {active} {hands} {move_number}"


def _decode_map(mode: GameMode) -> dict[str, str]:
    mapping = dict(_SFEN_TO_TYPE)
    for piece_type in mode.pieces.all_types():
        symbol = piece_type.sfen_symbol
        if symbol:
            mapping[symbol.lower()] = piece_type.id.name
    return mapping


def _encode_map(mode: GameMode | None) -> dict[str, str]:
    mapping = {name: symbol for symbol, name in _SFEN_TO_TYPE.items()}
    mapping.update({"tokin": "+p", "horse": "+b", "dragon": "+r"})
    if mode is None:
        return mapping
    for piece_type in mode.pieces.all_types():
        if piece_type.sfen_symbol:
            mapping[piece_type.id.name] = piece_type.sfen_symbol
    return mapping


def _piece_sfen(piece: Piece, to_symbol: dict[str, str]) -> str:
    symbol = to_symbol.get(piece.piece_type.name)
    if symbol is None:
        raise ValueError(f"piece cannot be represented in SFEN: {piece.piece_type.name}")
    letters = symbol[1:] if symbol.startswith("+") else symbol
    letters = letters.upper() if piece.side is PieceSide.WHITE else letters.lower()
    return f"+{letters}" if symbol.startswith("+") else letters


def _parse_hands(token: str, to_type: dict[str, str]) -> HandsState:
    hands = HandsState()
    if token in {"-", ""}:
        return hands
    index = 0
    while index < len(token):
        count = 1
        if token[index].isdigit():
            digits = token[index]
            index += 1
            while index < len(token) and token[index].isdigit():
                digits += token[index]
                index += 1
            count = int(digits)
        if index >= len(token):
            raise ValueError("invalid SFEN hands")
        char = token[index]
        index += 1
        name = to_type.get(char.lower())
        if name is None:
            raise ValueError(f"unsupported SFEN hand piece: {char!r}")
        side = PieceSide.WHITE if char.isupper() else PieceSide.BLACK
        for _ in range(count):
            hands.add(side, Piece(PieceTypeId(name), side))
    return hands


def _hands_sfen(hands: HandsState | None, to_symbol: dict[str, str]) -> str:
    if hands is None:
        return "-"
    parts: list[str] = []
    for side, upper in ((PieceSide.WHITE, True), (PieceSide.BLACK, False)):
        counts: Counter[str] = Counter()
        for piece in hands.by_side.get(side, ()):
            symbol = to_symbol.get(piece.piece_type.name, piece.piece_type.name[0]).lstrip("+")
            counts[symbol.lower()] += 1
        for letter in _HAND_ORDER:
            count = counts.get(letter, 0)
            if count == 0:
                continue
            token = letter.upper() if upper else letter
            parts.append(f"{count if count > 1 else ''}{token}")
    return "".join(parts) or "-"
