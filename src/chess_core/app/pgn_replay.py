"""Replay imported PGN movetext onto a GameRecord / LocalGameService."""

from __future__ import annotations

import re

from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn, parse_square, square_name
from chess_core.core.pgn import PGN_RESULTS, PgnGame, _RESULT_ALIASES, _tokenize_movetext
from chess_core.core.piece import PieceTypeId
from chess_core.core.state import GameState

_MOVE_NUMBER_RE = re.compile(r"^\d+\.+$")
_ATTACHED_MOVE_NUMBER_RE = re.compile(r"^\d+\.(?:\.\.)?(.*)$")
_COORDINATE_RE = re.compile(
    r"^([a-z]+)(\d+)[-x]?([a-z]+)(\d+)(?:[:=]([qrbnQRBN]))?$"
)
_UCI_PROMO_RE = re.compile(r"^([a-z]+)(\d+)([a-z]+)(\d+)([qrbnQRBN])$")
_DROP_RE = re.compile(r"^([A-Z]?)@([a-z]+\d+)$")
_BLOCKER_RE = re.compile(r"^@([a-z]+\d+)$")
_PROMO_MAP = {"q": "queen", "r": "rook", "b": "bishop", "n": "knight"}


def looks_like_pgn(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("[") or bool(re.search(r"\b1\.", stripped))


def move_tokens_from_game(game: PgnGame) -> tuple[str, ...]:
    return move_tokens_from_movetext(game.moves)


def structural_tokens(moves: str) -> tuple[str, ...]:
    """Movetext tokens with comments removed and parentheses split out.

    ``(`` and ``)`` stay as their own tokens so a walker can enter variations.
    The main line is everything at parenthesis depth zero.
    """
    pieces: list[str] = []
    for token in _tokenize_movetext(moves):
        if token.startswith("{") or token.startswith(";"):
            continue
        pieces.extend(_split_parens(token))
    return tuple(pieces)


def move_tokens_from_movetext(moves: str) -> tuple[str, ...]:
    """SAN/coordinate tokens of the main line. Variations in ``()`` are skipped."""
    tokens: list[str] = []
    depth = 0
    for token in structural_tokens(moves):
        if token == "(":
            depth += 1
            continue
        if token == ")":
            if depth:
                depth -= 1
            continue
        if depth:
            continue
        body = _move_body(token)
        if body:
            tokens.append(body)
    return tuple(tokens)


def _move_body(token: str) -> str | None:
    """Playable move text, or ``None`` for numbers, results, NAGs and markers."""
    if not token or token in "()":
        return None
    if token.startswith("{") or token.startswith(";") or token.startswith("$"):
        return None
    if token in _RESULT_ALIASES or token in PGN_RESULTS:
        return None
    if set(token) <= {"."}:
        return None
    attached = _ATTACHED_MOVE_NUMBER_RE.match(token)
    if attached:
        token = attached.group(1)
        if not token:
            return None
    if _MOVE_NUMBER_RE.match(token):
        return None
    if re.fullmatch(r"(?i)e\.?p\.?", token):
        return None
    body = token.rstrip("?!")
    return body or None


def _split_parens(token: str) -> list[str]:
    pieces: list[str] = []
    buf: list[str] = []
    for char in token:
        if char in "()":
            if buf:
                pieces.append("".join(buf))
                buf.clear()
            pieces.append(char)
        else:
            buf.append(char)
    if buf:
        pieces.append("".join(buf))
    return pieces


def resolve_turn(state: GameState, token: str, generator: MoveGenerator | None = None) -> Turn:
    parts = [part for part in token.split("·") if part]
    if not parts:
        raise ValueError("empty PGN move")
    actions = [
        _resolve_action(state, part, generator, part_index)
        for part_index, part in enumerate(parts)
    ]
    return Turn(state.side_to_move, actions)


def _resolve_action(
    state: GameState,
    token: str,
    generator: MoveGenerator | None,
    part_index: int,
) -> MoveAction | DropAction | PlaceBlockerAction:
    cleaned = _clean_move_token(token)
    shape = state.board_state.board.shape
    drop = _DROP_RE.match(cleaned)
    if drop and drop.group(1):
        letter, square_token = drop.groups()
        name = {"K": "king", "Q": "queen", "R": "rook", "B": "bishop", "N": "knight"}.get(
            letter, "pawn"
        )
        return DropAction(PieceTypeId(name), parse_square(square_token, shape.files, shape.ranks))
    blocker = _BLOCKER_RE.match(cleaned)
    if blocker:
        square = parse_square(blocker.group(1), shape.files, shape.ranks)
        if part_index == 0 and state.hands is not None:
            return DropAction(PieceTypeId("pawn"), square)
        return PlaceBlockerAction(square)
    coordinate = _parse_coordinate(cleaned, shape.files, shape.ranks)
    if coordinate is not None:
        return coordinate
    if generator is not None and part_index == 0:
        matched = _match_legal(state, cleaned, generator)
        if matched is not None:
            return matched
    raise ValueError(f"cannot parse PGN move: {token!r}")


def _parse_coordinate(token: str, files: int, ranks: int) -> MoveAction | None:
    promo = None
    match = _UCI_PROMO_RE.match(token) or _COORDINATE_RE.match(token)
    if match is None:
        return None
    from_file, from_rank, to_file, to_rank, promo_letter = match.groups()
    if promo_letter:
        promo = PieceTypeId(_PROMO_MAP[promo_letter.lower()])
    return MoveAction(
        parse_square(f"{from_file}{from_rank}", files, ranks),
        parse_square(f"{to_file}{to_rank}", files, ranks),
        promo,
    )


def _match_legal(state: GameState, token: str, generator: MoveGenerator) -> MoveAction | None:
    wanted = _normalize_san(token)
    if wanted in {"O-O", "O-O-O"}:
        return _match_castling(state, wanted, generator)
    matches: list[MoveAction] = []
    for action in generator.generate_legal(state):
        if not isinstance(action, MoveAction):
            continue
        turn = Turn(state.side_to_move, [action])
        after = state.apply_turn(turn, record_history=False)
        labels = _move_aliases(state, action, turn, after)
        if wanted in labels:
            matches.append(action)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous PGN move: {token!r}")
    return None


def _match_castling(state: GameState, token: str, generator: MoveGenerator) -> MoveAction | None:
    mode = state.extras.get("mode")
    rule = getattr(mode, "castling_rule", None)
    if rule is None:
        for action in generator.generate_legal(state):
            if not isinstance(action, MoveAction):
                continue
            piece = state.board_state.piece_at(action.from_square.index(state.board_state.board.shape.files))
            if piece is None or piece.piece_type.name != "king":
                continue
            delta = abs(action.to_square.file - action.from_square.file)
            if delta != 2:
                continue
            notation = "O-O" if action.to_square.file > action.from_square.file else "O-O-O"
            if notation == token:
                return action
        return None
    for action in generator.generate_legal(state):
        if not isinstance(action, MoveAction):
            continue
        path = rule.decode(action, state)
        if path is None:
            continue
        notation = "O-O" if path.rook_from.file > path.king_from.file else "O-O-O"
        if notation == token:
            return action
    return None


def _normalize_san(token: str) -> str:
    normalized = _clean_move_token(token).strip()
    normalized = re.sub(r"(?i)e\.?p\.?$", "", normalized).strip()
    normalized = normalized.replace("0", "O").replace("o", "O")
    if normalized.upper() in {"O-O", "O-O-O"}:
        return normalized.upper()
    normalized = re.sub(r"\(([KQRBNkqrbn])\)$", r"\1", normalized)
    normalized = normalized.replace("/", "").replace("=", "")
    normalized = normalized.replace("x", "").replace("X", "")
    normalized = normalized.replace("-", "").replace(":", "")
    if normalized and normalized[0] in "kqrbn":
        normalized = normalized[0].upper() + normalized[1:]
    return normalized


def _clean_move_token(token: str) -> str:
    cleaned = token.strip()
    cleaned = re.sub(r"[!?]+$", "", cleaned)
    cleaned = re.sub(r"(?:\+\+|[+#])$", "", cleaned)
    cleaned = re.sub(r"[!?]+$", "", cleaned)
    return cleaned


def _move_aliases(
    state: GameState,
    action: MoveAction,
    turn: Turn,
    after: GameState,
) -> set[str]:
    files = state.board_state.board.shape.files
    piece = state.board_state.piece_at(action.from_square.index(files))
    canonical = format_turn(
        turn,
        before=state,
        after=after,
        style=NotationStyle.PIECE_SQUARE,
    )
    coordinate = format_turn(
        turn,
        before=state,
        after=after,
        style=NotationStyle.FROM_TO,
    )
    source = square_name(action.from_square)
    target = square_name(action.to_square)
    promo = (
        _promotion_letter(action.promotion_choice.name)
        if action.promotion_choice is not None
        else ""
    )
    labels = {
        canonical,
        coordinate,
        f"{source}{target}{promo.lower()}",
    }
    if piece is not None:
        letter = {
            "king": "K",
            "queen": "Q",
            "rook": "R",
            "bishop": "B",
            "knight": "N",
            "pawn": "",
        }.get(piece.piece_type.name, piece.piece_type.name[:1].upper())
        promotion = f"={promo}" if promo else ""
        if letter:
            labels.update(
                {
                    f"{letter}{target}{promotion}",
                    f"{letter}{source[0]}{target}{promotion}",
                    f"{letter}{source[1:]}{target}{promotion}",
                    f"{letter}{source}{target}{promotion}",
                }
            )
        else:
            labels.update(
                {
                    f"{target}{promotion}",
                    f"{source[0]}{target}{promotion}",
                    f"{source}{target}{promotion}",
                }
            )
    return {_normalize_san(label) for label in labels}


def _promotion_letter(name: str) -> str:
    return {"queen": "Q", "rook": "R", "bishop": "B", "knight": "N"}.get(
        name,
        name[:1].upper(),
    )
