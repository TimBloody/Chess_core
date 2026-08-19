"""FEN import/export and move notation for chess-like games."""

from __future__ import annotations

from enum import Enum, auto
from collections.abc import Callable

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import (
    Action,
    DropAction,
    MoveAction,
    PlaceAction,
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
_CHECKERS_SYMBOL_TO_TYPE = {
    "m": "checker_man",
    "k": "checker_king",
}
_CHECKERS_TYPE_TO_SYMBOL = {
    "checker_man": "m",
    "checker_king": "k",
}

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
    if isinstance(action, PlaceAction):
        letter = _PIECE_LETTER.get(action.piece_type.name, action.piece_type.name[0].upper())
        target = square_name(action.to_square)
        return f"{letter}+{target}" if letter else f"+{target}"
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
    if action.captured_squares:
        hops = action.path or (target,)
        return ":".join(square_name(square) for square in (source, *hops))
    castling = _castling_text(action, before)
    is_capture = captured is not None or _is_en_passant(action, piece, before)
    if style is NotationStyle.FROM_TO:
        sep = "x" if is_capture else "-"
        text = f"{square_name(source)}{sep}{square_name(target)}"
    elif castling is not None:
        text = castling
    else:
        letter = ""
        if piece is not None:
            letter = _PIECE_LETTER.get(piece.piece_type.name, piece.piece_type.name[0].upper())
        if letter:
            disambiguation = _disambiguation(action, piece, before)
            capture_marker = "x" if is_capture else ""
            text = f"{letter}{disambiguation}{capture_marker}{square_name(target)}"
        elif is_capture:
            text = f"{square_name(source)[0]}x{square_name(target)}"
        else:
            text = square_name(target)
    if action.promotion_choice is not None:
        promo = _PIECE_LETTER.get(action.promotion_choice.name, action.promotion_choice.name[0].upper())
        if promo:
            text += f"={promo}"
    if style is NotationStyle.PIECE_SQUARE:
        text += _check_suffix(before, after)
    return text


def _castling_text(action: MoveAction, before: GameState) -> str | None:
    mode = before.extras.get("mode")
    rule = getattr(mode, "castling_rule", None)
    if rule is None:
        return None
    path = rule.decode(action, before)
    if path is None:
        return None
    return "O-O" if path.rook_from.file > path.king_from.file else "O-O-O"


def _is_en_passant(
    action: MoveAction,
    piece: Piece | None,
    before: GameState,
) -> bool:
    return (
        piece is not None
        and piece.piece_type.name == "pawn"
        and action.from_square.file != action.to_square.file
        and before.extras.get("en_passant") == action.to_square
    )


def _disambiguation(
    action: MoveAction,
    piece: Piece,
    before: GameState,
) -> str:
    if piece.piece_type.name in {"pawn", "king"}:
        return ""
    mode = before.extras.get("mode")
    if not isinstance(mode, GameMode):
        return ""
    from chess_core.core.movegen import MoveGenerator

    files = before.board_state.board.shape.files
    competing_sources = {
        candidate.from_square
        for candidate in MoveGenerator(mode).generate_legal(before)
        if isinstance(candidate, MoveAction)
        and candidate.to_square == action.to_square
        and candidate.from_square != action.from_square
        and (
            (candidate_piece := before.board_state.piece_at(
                candidate.from_square.index(files)
            ))
            is not None
        )
        and candidate_piece.side is piece.side
        and candidate_piece.piece_type == piece.piece_type
    }
    if not competing_sources:
        return ""
    if all(other.file != action.from_square.file for other in competing_sources):
        return square_name(action.from_square)[0]
    if all(other.rank != action.from_square.rank for other in competing_sources):
        return str(action.from_square.rank + 1)
    return square_name(action.from_square)


def _check_suffix(before: GameState, after: GameState) -> str:
    mode = before.extras.get("mode")
    if not isinstance(mode, GameMode) or not mode.protects_royal():
        return ""
    from chess_core.core.movegen import MoveGenerator

    generator = MoveGenerator(mode)
    if not generator.is_in_check(after):
        return ""
    return "#" if generator.is_checkmate(after) else "+"


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
            name = _fen_symbol_to_type(mode).get(char.lower())
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


def encode_board_placement(
    state: GameState,
    token_for_piece: Callable[[Piece], str | None],
) -> str:
    """Rank-major FEN/SFEN placement: last rank first, empty runs as digits."""
    shape = state.board_state.board.shape
    rows: list[str] = []
    for rank in reversed(range(shape.ranks)):
        row = ""
        empty = 0
        for file in range(shape.files):
            piece = state.board_state.piece_at(rank * shape.files + file)
            token = None if piece is None else token_for_piece(piece)
            if token is None:
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            row += token
        if empty:
            row += str(empty)
        rows.append(row)
    return "/".join(rows)


def _uses_checkers_fen(mode: object) -> bool:
    pieces = getattr(mode, "pieces", None)
    if pieces is None:
        return False
    try:
        return any(piece_type.id.name.startswith("checker") for piece_type in pieces.all_types())
    except Exception:
        return False


def _fen_symbol_to_type(mode: object) -> dict[str, str]:
    if _uses_checkers_fen(mode):
        return _CHECKERS_SYMBOL_TO_TYPE
    return _SYMBOL_TO_TYPE


def _fen_type_to_symbol(mode: object) -> dict[str, str]:
    if _uses_checkers_fen(mode):
        return _CHECKERS_TYPE_TO_SYMBOL
    return _TYPE_TO_SYMBOL


def to_fen(state: GameState) -> str:
    type_to_symbol = _fen_type_to_symbol(state.extras.get("mode"))

    def token(piece: Piece) -> str:
        symbol = type_to_symbol.get(piece.piece_type.name)
        if symbol is None:
            raise ValueError(
                f"piece cannot be represented in FEN: {piece.piece_type.name}"
            )
        return symbol.upper() if piece.side is PieceSide.WHITE else symbol

    placement = encode_board_placement(state, token)
    active = "w" if state.side_to_move is PieceSide.WHITE else "b"
    rights = "".join(
        char for char in "KQkq" if char in state.extras.get("castling_rights", ())
    ) or "-"
    en_passant = (
        square_name(state.extras.get("en_passant"))
        if state.extras.get("en_passant")
        else "-"
    )
    return (
        f"{placement} {active} {rights} {en_passant} "
        f"{state.extras.get('halfmove_clock', 0)} {state.extras.get('fullmove_number', 1)}"
    )


def parse_square(name: str, files: int, ranks: int) -> Square:
    token = name.strip().lower()
    letters = 0
    while letters < len(token) and token[letters].isalpha():
        letters += 1
    if letters == 0 or letters == len(token) or not token[letters:].isdigit():
        raise ValueError("invalid FEN square")
    file_token = token[:letters]
    file = 0
    for char in file_token:
        file = file * 26 + (ord(char) - ord("a") + 1)
    file -= 1
    square = Square(file, int(token[letters:]) - 1)
    Square.from_index(square.index(files), files, ranks)
    return square

def _square_name(square: Square) -> str:
    return square_name(square)


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
