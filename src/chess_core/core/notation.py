"""FEN import/export and move notation for chess-like games."""

from __future__ import annotations

from enum import Enum, auto

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import (
    Action,
    DropAction,
    MoveAction,
    PassAction,
    PlaceBlockerAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.repetition import seed_repetition_log
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
    "k": "king",
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
    return seed_repetition_log(GameState(BoardState(mode.board, cells), side, extras=extras))


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
            raise ValueError("UCI promotion must be q, r, b, n, or k")
        promotion = PieceTypeId(name)
    return MoveAction(origin, target, promotion)


def format_uci(action: MoveAction) -> str:
    text = f"{square_name(action.from_square)}{square_name(action.to_square)}"
    if action.promotion_choice is None:
        return text
    letter = _TYPE_TO_UCI_PROMOTION.get(action.promotion_choice.name)
    return f"{text}{letter}" if letter else text


def format_engine_token(action: Action) -> str:
    """UCI-like token for engine PV: moves, drops ``P@e4``, duck ``@c4``."""
    if isinstance(action, MoveAction):
        return format_uci(action)
    if isinstance(action, DropAction):
        letter = _TYPE_TO_SYMBOL.get(action.piece_type.name, action.piece_type.name[:1])
        face = action.face or action.piece_type.name
        if action.face is not None:
            letter = _TYPE_TO_SYMBOL.get(face, face[:1])
        return f"{letter.upper()}@{square_name(action.to_square)}"
    if isinstance(action, PlaceBlockerAction):
        return f"@{square_name(action.square)}"
    if isinstance(action, PassAction):
        return "0000"
    return "?"


def normalize_engine_token(token: str) -> str:
    """Canonical form for matching: lowercase, strip Fairy shogi ``+``/``-`` suffixes."""
    text = token.strip().lower()
    if "@" not in text and len(text) >= 5 and text[-1] in "+-":
        return text[:-1]
    return text


def engine_token_aliases(action: Action, *, mode_id: str = "", files: int = 8, ranks: int = 8) -> tuple[str, ...]:
    """Tokens an external engine might emit for ``action`` (UCI, USI, Fairy +/- / +P@)."""
    seen: list[str] = []
    for token in _engine_token_alias_iter(action, mode_id=mode_id, files=files, ranks=ranks):
        if token and token not in seen:
            seen.append(token)
    return tuple(seen)


def format_engine_turn(turn: Turn) -> str:
    return ",".join(format_engine_token(action) for action in turn.actions)


def to_engine_fen(state: GameState) -> str:
    """FEN for a UCI engine: chess/crazyhouse, or Fairy-Stockfish shogi variants."""
    mode = state.extras.get("mode")
    mode_id = mode.id if isinstance(mode, GameMode) else ""
    if mode_id in {"duck", "duck_chess"}:
        return _to_duck_fen(state)
    symbols = _FAIRY_FEN_SYMBOLS.get(mode_id)
    if symbols is not None:
        return _to_fairy_fen(state, symbols)
    fen = to_fen(state)
    if state.hands is not None:
        board, rest = fen.split(" ", 1)
        fen = f"{board}[{_pocket_fen(state)}] {rest}"
    partner = state.extras.get("partner_engine_fen")
    if isinstance(partner, str) and partner.strip():
        return f"{fen} | {partner.strip()}"
    return fen


def with_partner_engine_fen(state: GameState, partner: GameState) -> GameState:
    """Clone ``state`` and attach the partner board as Fairy two-board FEN."""
    clone = state.clone(include_history=False)
    clone.extras["partner_engine_fen"] = to_engine_fen(partner)
    return clone


_SHOGI_TO_SFEN = {
    "king": "k",
    "gold": "g",
    "silver": "s",
    "knight": "n",
    "lance": "l",
    "pawn": "p",
    "bishop": "b",
    "rook": "r",
    "tokin": "+p",
    "promoted_lance": "+l",
    "promoted_knight": "+n",
    "promoted_silver": "+s",
    "horse": "+b",
    "dragon": "+r",
}
_SFEN_HAND_ORDER = ("rook", "bishop", "gold", "silver", "knight", "lance", "pawn")

# Fairy-Stockfish UCI_Variant piece letters (not chess FEN).
_FAIRY_FEN_SYMBOLS: dict[str, dict[str, str]] = {
    "shogi": _SHOGI_TO_SFEN,
    "reversi": {
        "disc": "p",
    },
    "dobutsu_shogi": {
        "chick": "c",
        "elephant": "e",
        "giraffe": "g",
        "lion": "l",
        "hen": "h",
    },
    "kyoto_shogi": {
        "king": "k",
        "pawn": "p",
        "rook": "r",
        "lance": "l",
        "tokin": "+l",
        "silver": "s",
        "bishop": "b",
        "gold": "+n",
        "knight": "n",
    },
}


def to_sfen(state: GameState) -> str:
    """USI SFEN for standard shogi-like pieces. Raises if a piece is not mappable."""
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
            symbol = _SHOGI_TO_SFEN.get(piece.piece_type.name)
            if symbol is None:
                raise ValueError(f"piece cannot be represented in SFEN: {piece.piece_type.name}")
            if piece.side is PieceSide.WHITE:
                symbol = symbol.upper() if not symbol.startswith("+") else "+" + symbol[1].upper()
            row += symbol
        if empty:
            row += str(empty)
        rows.append(row)
    side = "b" if state.side_to_move is PieceSide.WHITE else "w"
    hands = _sfen_hands(state)
    ply = int(state.extras.get("fullmove_number", 1))
    return f"{'/'.join(rows)} {side} {hands} {ply}"


def format_usi_square(square: Square, *, files: int, ranks: int) -> str:
    file_number = files - square.file
    rank_letter = chr(ord("a") + (ranks - 1 - square.rank))
    return f"{file_number}{rank_letter}"


def format_usi_action(action: Action, *, files: int = 9, ranks: int = 9) -> str:
    if isinstance(action, MoveAction):
        text = (
            f"{format_usi_square(action.from_square, files=files, ranks=ranks)}"
            f"{format_usi_square(action.to_square, files=files, ranks=ranks)}"
        )
        if action.promotion_choice is not None:
            text += "+"
        return text
    if isinstance(action, DropAction):
        letter = _SHOGI_TO_SFEN.get(action.piece_type.name, action.piece_type.name[:1]).upper().replace("+", "")
        return f"{letter}*{format_usi_square(action.to_square, files=files, ranks=ranks)}"
    raise ValueError(f"unsupported USI action: {type(action).__name__}")


def _pocket_fen(state: GameState) -> str:
    if state.hands is None:
        return ""
    white = "".join(
        (_TYPE_TO_SYMBOL.get(piece.piece_type.name, piece.piece_type.name[:1]) or "?").upper()
        for piece in state.hands.by_side.get(PieceSide.WHITE, ())
    )
    black = "".join(
        (_TYPE_TO_SYMBOL.get(piece.piece_type.name, piece.piece_type.name[:1]) or "?")
        for piece in state.hands.by_side.get(PieceSide.BLACK, ())
    )
    return white + black


def _sfen_hands(state: GameState) -> str:
    if state.hands is None:
        return "-"
    parts: list[str] = []
    for side, upper in ((PieceSide.WHITE, True), (PieceSide.BLACK, False)):
        counts: dict[str, int] = {}
        for piece in state.hands.by_side.get(side, ()):
            counts[piece.piece_type.name] = counts.get(piece.piece_type.name, 0) + 1
        for name in _SFEN_HAND_ORDER:
            count = counts.get(name, 0)
            if count <= 0:
                continue
            letter = _SHOGI_TO_SFEN[name].upper() if upper else _SHOGI_TO_SFEN[name]
            parts.append(f"{count if count > 1 else ''}{letter}")
    return "".join(parts) or "-"


def _to_fairy_fen(state: GameState, symbols: dict[str, str]) -> str:
    """Fairy-Stockfish shogi-template FEN: ``board[hand] w 0 1``."""
    rows: list[str] = []
    shape = state.board_state.board.shape
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
            symbol = symbols.get(piece.piece_type.name)
            if symbol is None:
                raise ValueError(f"piece cannot be represented for the engine: {piece.piece_type.name}")
            row += _colored_fen_symbol(symbol, piece.side)
        if empty:
            row += str(empty)
        rows.append(row)
    hand = _fairy_hand(state, symbols)
    side = "w" if state.side_to_move is PieceSide.WHITE else "b"
    ply = int(state.extras.get("fullmove_number", 1))
    return f"{'/'.join(rows)}[{hand}] {side} 0 {ply}"


def _to_duck_fen(state: GameState) -> str:
    """Fairy-Stockfish Duck FEN, where the neutral blocker is ``*``."""
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
            if piece.side is PieceSide.NEUTRAL and piece.piece_type.name == "blocker":
                row += "*"
                continue
            symbol = _TYPE_TO_SYMBOL.get(piece.piece_type.name)
            if symbol is None:
                raise ValueError(
                    f"piece cannot be represented for Duck engine: {piece.piece_type.name}"
                )
            row += symbol.upper() if piece.side is PieceSide.WHITE else symbol
        if empty:
            row += str(empty)
        rows.append(row)
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
        f"{'/'.join(rows)} {active} {rights} {en_passant} "
        f"{state.extras.get('halfmove_clock', 0)} "
        f"{state.extras.get('fullmove_number', 1)}"
    )


def _fairy_hand(state: GameState, symbols: dict[str, str]) -> str:
    if state.hands is None:
        return "-"
    parts: list[str] = []
    for side in (PieceSide.WHITE, PieceSide.BLACK):
        for piece in state.hands.by_side.get(side, ()):
            symbol = symbols.get(piece.piece_type.name)
            if symbol is None:
                raise ValueError(f"hand piece cannot be represented for the engine: {piece.piece_type.name}")
            parts.append(_colored_fen_symbol(symbol, side))
    return "".join(parts) or "-"


def _colored_fen_symbol(symbol: str, side: PieceSide) -> str:
    if side is PieceSide.WHITE:
        return symbol.upper() if not symbol.startswith("+") else "+" + symbol[1].upper()
    return symbol


def _engine_token_alias_iter(action: Action, *, mode_id: str, files: int, ranks: int):
    primary = format_engine_token(action)
    yield primary
    if isinstance(action, MoveAction):
        try:
            yield format_usi_action(action, files=files, ranks=ranks)
        except ValueError:
            return
        return
    if isinstance(action, DropAction):
        target = square_name(action.to_square)
        face = action.face or action.piece_type.name
        yield from (f"{letter}@{target}" for letter in _fairy_drop_letters(face, mode_id))


# Fairy drops a promoted Kyoto face as ``+P@a3`` (not ``R@a3``).
_FAIRY_PROMOTED_DROP_LETTER = {
    "rook": "+P",
    "bishop": "+S",
    "gold": "+N",
    "tokin": "+L",
    "hen": "+C",
}


def _fairy_drop_letters(face: str, mode_id: str) -> tuple[str, ...]:
    letters: list[str] = []
    promoted = _FAIRY_PROMOTED_DROP_LETTER.get(face)
    if promoted is not None:
        letters.append(promoted)
    symbols = _FAIRY_FEN_SYMBOLS.get(mode_id, {})
    symbol = symbols.get(face)
    if symbol:
        letter = symbol.upper() if not symbol.startswith("+") else "+" + symbol[1].upper()
        letters.append(letter)
    return tuple(dict.fromkeys(letters))


def _square_name(square: Square) -> str:
    return square_name(square)
