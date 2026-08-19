"""PGN import/export for recorded games."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import DropAction, MoveAction, PlaceBlockerAction, Turn
from chess_core.core.notation import (
    NotationStyle,
    format_turn,
    parse_square,
    square_name,
    to_fen,
)
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.core.state import GameState

_HEADER_RE = re.compile(r'\[(\w+)\s+"(.*)"\]')
_MOVE_NUMBER_RE = re.compile(r"^\d+\.+$")
_ATTACHED_MOVE_NUMBER_RE = re.compile(r"^\d+\.(?:\.\.)?(.*)$")
_COORDINATE_RE = re.compile(
    r"^([a-z]+)(\d+)[-x]?([a-z]+)(\d+)(?:[:=]([qrbnQRBN]))?$"
)
_UCI_PROMO_RE = re.compile(r"^([a-z]+)(\d+)([a-z]+)(\d+)([qrbnQRBN])$")
_DROP_RE = re.compile(r"^([A-Z]?)@([a-z]+\d+)$")
_BLOCKER_RE = re.compile(r"^@([a-z]+\d+)$")
_RESULTS = frozenset({"1-0", "0-1", "1/2-1/2", "*"})
_PROMO_MAP = {"q": "queen", "r": "rook", "b": "bishop", "n": "knight"}
_SEVEN_TAG_ROSTER = ("Event", "Site", "Date", "Round", "White", "Black", "Result")


@dataclass(frozen=True, slots=True)
class PgnGame:
    headers: dict[str, str]
    moves: tuple[str, ...]
    result: str = "*"


def looks_like_pgn(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("[") or bool(re.search(r"\b1\.", stripped))


def export_pgn(
    *,
    mode: GameMode,
    initial: GameState,
    notations: list[str],
    headers: Mapping[str, str] | None = None,
    result: str = "*",
) -> str:
    payload = {
        "Event": "Chess Core",
        "Site": "?",
        "Date": date.today().isoformat().replace("-", "."),
        "Round": "?",
        "White": "?",
        "Black": "?",
        "Result": result,
        "Variant": mode.name,
    }
    if headers:
        payload.update({key: str(value) for key, value in headers.items()})
    effective_result = payload["Result"]
    if effective_result not in _RESULTS:
        raise ValueError(f"unsupported PGN result: {effective_result!r}")
    try:
        start_fen = to_fen(initial)
        default_fen = to_fen(mode.initial_state())
    except ValueError:
        from chess_core.core.sfen import to_sfen

        start_sfen = to_sfen(initial)
        default_sfen = to_sfen(mode.initial_state())
        if start_sfen != default_sfen:
            payload["SetUp"] = "1"
            payload["SFEN"] = start_sfen
    else:
        if start_fen != default_fen:
            payload["SetUp"] = "1"
            payload["FEN"] = start_fen
    ordered_keys = list(_SEVEN_TAG_ROSTER)
    ordered_keys.extend(key for key in payload if key not in _SEVEN_TAG_ROSTER)
    lines = [
        f'[{key} "{_escape_header_value(payload[key])}"]'
        for key in ordered_keys
    ]
    lines.append("")
    lines.append(_format_movetext(notations, initial.side_to_move, effective_result))
    return "\n".join(lines) + "\n"


def parse_pgn(text: str) -> PgnGame:
    headers: dict[str, str] = {}
    move_text_parts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _HEADER_RE.match(line)
        if match:
            headers[match.group(1)] = _unescape_header_value(match.group(2))
            continue
        move_text_parts.append(line)
    uncommented = _strip_comments("\n".join(move_text_parts))
    uncommented = re.sub(
        r"([a-z]+\d+)\(([KQRBNkqrbn])\)",
        r"\1=\2",
        uncommented,
    )
    move_text = _strip_variations(uncommented)
    tokens = [token for token in move_text.split() if token]
    moves: list[str] = []
    result = headers.get("Result", "*")
    for token in tokens:
        attached = _ATTACHED_MOVE_NUMBER_RE.match(token)
        if attached:
            token = attached.group(1)
            if not token:
                continue
        if token in _RESULTS:
            result = token
            continue
        if _MOVE_NUMBER_RE.match(token):
            continue
        if _is_en_passant_marker(token):
            continue
        moves.append(token.rstrip("?!"))
    return PgnGame(headers=headers, moves=tuple(moves), result=result)


def _format_movetext(
    notations: list[str],
    starting_side: PieceSide,
    result: str,
) -> str:
    if not notations:
        return result
    body: list[str] = []
    move_number = 1
    side = starting_side
    for notation in notations:
        if side is PieceSide.WHITE:
            body.append(f"{move_number}. {notation}")
            side = PieceSide.BLACK
        else:
            prefix = f"{move_number}... " if not body or body[-1].endswith("... ") else ""
            if prefix:
                body.append(f"{prefix}{notation}")
            else:
                body[-1] = f"{body[-1]} {notation}"
            move_number += 1
            side = PieceSide.WHITE
    return f"{' '.join(body)} {result}"


def _escape_header_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


def _unescape_header_value(value: str) -> str:
    return re.sub(r"\\([\\\"])", r"\1", value)


def replay_pgn(pgn: PgnGame, mode: GameMode, initial: GameState | None = None) -> GameState:
    from chess_core.core.movegen import MoveGenerator

    state = (initial or mode.initial_state()).clone(include_history=False)
    state.extras["mode"] = mode
    generator = MoveGenerator(mode)
    for token in pgn.moves:
        turn = resolve_turn(state, token, generator)
        state = state.apply_turn(turn)
    return state


def resolve_turn(state: GameState, token: str, generator: object | None = None) -> Turn:
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
    generator: object | None,
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


def _match_legal(state: GameState, token: str, generator: object) -> MoveAction | None:
    from chess_core.core.movegen import MoveGenerator

    assert isinstance(generator, MoveGenerator)
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


def _match_castling(state: GameState, token: str, generator: object) -> MoveAction | None:
    from chess_core.core.movegen import MoveGenerator

    assert isinstance(generator, MoveGenerator)
    mode = state.extras.get("mode")
    rule = getattr(mode, "castling_rule", None)
    if rule is None:
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


def _strip_comments(text: str) -> str:
    without_braces = re.sub(r"\{[^}]*\}", " ", text)
    without_nags = re.sub(r"\$\d+", " ", without_braces)
    without_lines = re.sub(r";[^\n]*", " ", without_nags)
    return without_lines


def _strip_variations(text: str) -> str:
    output: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif depth == 0:
            output.append(char)
    return "".join(output)


def _is_en_passant_marker(token: str) -> bool:
    return bool(re.fullmatch(r"(?i)e\.?p\.?", token.strip()))
