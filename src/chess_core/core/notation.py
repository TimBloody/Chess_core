"""FEN import/export and move notation for chess-like games."""

from __future__ import annotations

from enum import Enum, auto

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import (
    Action,
    DropAction,
    MoveAction,
    PlaceBlockerAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState

_SYMBOL_TO_TYPE = {
    "k": "king",
    "q": "queen",
    "r": "rook",
    "b": "bishop",
    "n": "knight",
    "p": "pawn",
}
_TYPE_TO_SYMBOL = {name: symbol for symbol, name in _SYMBOL_TO_TYPE.items()}

_PIECE_LETTER = {
    "king": "K",
    "queen": "Q",
    "rook": "R",
    "bishop": "B",
    "knight": "N",
    "pawn": "",
}
_UCI_PROMOTIONS = {
    "q": "queen",
    "r": "rook",
    "b": "bishop",
    "n": "knight",
}
_TYPE_TO_UCI_PROMOTION = {name: letter for letter, name in _UCI_PROMOTIONS.items()}


class NotationStyle(Enum):
    FROM_TO = auto()
    PIECE_SQUARE = auto()


def square_name(square: Square) -> str:
    return f"{chr(ord('a') + square.file)}{square.rank + 1}"


def format_action(
    action: Action,
    *,
    before: GameState,
    after: GameState,
    style: NotationStyle = NotationStyle.FROM_TO,
) -> str:
    files = before.board_state.board.shape.files
    if isinstance(action, MoveAction):
        return _format_move(action, before, after, style, files)
    if isinstance(action, DropAction):
        letter = _PIECE_LETTER.get(action.piece_type.name, action.piece_type.name[0].upper())
        target = square_name(action.to_square)
        return f"{letter}@{target}" if letter else f"@{target}"
    if isinstance(action, PlaceBlockerAction):
        return f"@{square_name(action.square)}"
    return "?"


def format_turn(
    turn: Turn,
    *,
    before: GameState,
    after: GameState,
    style: NotationStyle = NotationStyle.FROM_TO,
) -> str:
    parts = [
        format_action(action, before=before, after=after, style=style)
        for action in turn.actions
    ]
    return "·".join(parts)


def _format_move(
    action: MoveAction,
    before: GameState,
    after: GameState,
    style: NotationStyle,
    files: int,
) -> str:
    source = action.from_square
    target = action.to_square
    piece = before.board_state.piece_at(source.index(files))
    captured = before.board_state.piece_at(target.index(files))
    is_capture = captured is not None
    if style is NotationStyle.FROM_TO:
        sep = "x" if is_capture else "-"
        text = f"{square_name(source)}{sep}{square_name(target)}"
    else:
        letter = ""
        if piece is not None:
            letter = _PIECE_LETTER.get(piece.piece_type.name, piece.piece_type.name[0].upper())
        if is_capture and letter:
            text = f"{letter}x{square_name(target)}"
        elif letter:
            text = f"{letter}{square_name(target)}"
        else:
            text = square_name(target)
    if action.promotion_choice is not None:
        promo = _PIECE_LETTER.get(action.promotion_choice.name, action.promotion_choice.name[0].upper())
        if promo:
            text += f"={promo}"
    return text


def parse_fen(fen: str, mode: GameMode) -> GameState:
    fields = fen.strip().split()
    if len(fields) not in {1, 6}:
        raise ValueError("FEN must contain either placement or six fields")
    rows = fields[0].split("/")
    shape = mode.board.shape
    if len(rows) != shape.ranks:
        raise ValueError("FEN rank count does not match board")
    cells: dict[int, Piece | None] = {
        index: None for index in range(shape.cell_count)
    }
    for fen_row, token in enumerate(rows):
        rank = shape.ranks - 1 - fen_row
        file = 0
        digits = ""
        for char in token:
            if char.isdigit():
                digits += char
                continue
            if digits:
                file += int(digits)
                digits = ""
            name = _SYMBOL_TO_TYPE.get(char.lower())
            if name is None:
                raise ValueError(f"unsupported FEN piece: {char!r}")
            if file >= shape.files:
                raise ValueError("FEN rank exceeds board width")
            side = PieceSide.WHITE if char.isupper() else PieceSide.BLACK
            cells[rank * shape.files + file] = Piece(PieceTypeId(name), side)
            file += 1
        if digits:
            file += int(digits)
        if file != shape.files:
            raise ValueError("FEN rank width does not match board")
    side = PieceSide.WHITE
    extras: dict[str, object] = {"mode": mode}
    if len(fields) == 6:
        if fields[1] not in {"w", "b"}:
            raise ValueError("invalid FEN active color")
        side = PieceSide.WHITE if fields[1] == "w" else PieceSide.BLACK
        extras["castling_rights"] = set() if fields[2] == "-" else set(fields[2])
        extras["en_passant"] = None if fields[3] == "-" else parse_square(fields[3], shape.files, shape.ranks)
        extras["halfmove_clock"] = int(fields[4])
        extras["fullmove_number"] = int(fields[5])
    return GameState(BoardState(mode.board, cells), side, extras=extras)


def to_fen(state: GameState) -> str:
    shape = state.board_state.board.shape
    rows: list[str] = []
    for rank in reversed(range(shape.ranks)):
        row = ""
        empty = 0
        for file in range(shape.files):
            piece = state.board_state.piece_at(rank * shape.files + file)
            if piece is None:
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            symbol = _TYPE_TO_SYMBOL.get(piece.piece_type.name)
            if symbol is None:
                raise ValueError(f"piece cannot be represented in FEN: {piece.piece_type.name}")
            row += symbol.upper() if piece.side is PieceSide.WHITE else symbol
        if empty:
            row += str(empty)
        rows.append(row)
    active = "w" if state.side_to_move is PieceSide.WHITE else "b"
    rights = "".join(char for char in "KQkq" if char in state.extras.get("castling_rights", ())) or "-"
    en_passant = square_name(state.extras.get("en_passant")) if state.extras.get("en_passant") else "-"
    return f"{'/'.join(rows)} {active} {rights} {en_passant} {state.extras.get('halfmove_clock', 0)} {state.extras.get('fullmove_number', 1)}"


def parse_square(name: str, files: int, ranks: int) -> Square:
    if len(name) != 2 or not name[0].isalpha() or not name[1].isdigit():
        raise ValueError("invalid FEN square")
    square = Square(ord(name[0].lower()) - ord("a"), int(name[1]) - 1)
    Square.from_index(square.index(files), files, ranks)
    return square


def parse_uci(value: str, *, files: int = 8, ranks: int = 8) -> MoveAction:
    """Parse a UCI coordinate move such as ``e2e4`` or ``a7a8q``."""
    token = value.strip().lower()
    if len(token) not in {4, 5}:
        raise ValueError("UCI move must look like e2e4 or a7a8q")
    origin = parse_square(token[:2], files, ranks)
    target = parse_square(token[2:4], files, ranks)
    promotion = None
    if len(token) == 5:
        name = _UCI_PROMOTIONS.get(token[4])
        if name is None:
            raise ValueError("UCI promotion must be q, r, b, or n")
        promotion = PieceTypeId(name)
    return MoveAction(origin, target, promotion)


def format_uci(action: MoveAction) -> str:
    text = f"{square_name(action.from_square)}{square_name(action.to_square)}"
    if action.promotion_choice is None:
        return text
    letter = _TYPE_TO_UCI_PROMOTION.get(action.promotion_choice.name)
    return f"{text}{letter}" if letter else text

def _square_name(square: Square) -> str:
    return square_name(square)
