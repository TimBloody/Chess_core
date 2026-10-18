"""PGN game records: tags, movetext, ChessBase-friendly formatting.

Filesystem and encodings stay in infra. This module only parses and emits
PGN text with Unix newlines; infra converts to CRLF + UTF-8 BOM for
ChessBase 16.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from re import compile as regexp

SEVEN_TAG_ROSTER: tuple[str, ...] = (
    "Event",
    "Site",
    "Date",
    "Round",
    "White",
    "Black",
    "Result",
)

PGN_RESULTS: frozenset[str] = frozenset({"1-0", "0-1", "1/2-1/2", "*"})

_RESULT_ALIASES = {
    "1-0": "1-0",
    "0-1": "0-1",
    "1/2-1/2": "1/2-1/2",
    "1–0": "1-0",
    "0–1": "0-1",
    "½-½": "1/2-1/2",
    "1/2–1/2": "1/2-1/2",
    "*": "*",
}

# ChessBase 16 Variant tag for non-standard chess. Omit for classic.
CHESSBASE_VARIANT: dict[str, str] = {
    "chess960": "Chess960",
    "crazyhouse": "Crazyhouse",
    "giveaway": "Giveaway",
    "bughouse": "Bughouse",
    "hand_and_brain": "HandAndBrain",
    "minichess": "Minichess",
    "cylindrical": "Cylindrical",
    "duck": "Duck",
    "shogi": "Shogi",
    "kyoto_shogi": "KyotoShogi",
    "dobutsu_shogi": "DobutsuShogi",
    "reversi": "Reversi",
    "corners": "Corners",
    "draughts": "Draughts",
    "gobblet": "Gobblet",
    "fairy": "Fairy",
    "fairytale": "Fairy",
}

_TAG_LINE = regexp(r'^\s*\[(\S+)\s+"(.*)"\]\s*$')
_DATE_YMD = regexp(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")

_ROSTER_DEFAULTS: dict[str, str] = {
    "Event": "Chess Core",
    "Site": "?",
    "Date": "????.??.??",
    "Round": "-",
    "White": "?",
    "Black": "?",
    "Result": "*",
}


@dataclass(frozen=True, slots=True)
class PgnGame:
    """One PGN game: ordered tags plus movetext without the final result token."""

    tags: tuple[tuple[str, str], ...]
    moves: str = ""
    comment: str = ""

    def tag(self, name: str, default: str = "") -> str:
        lowered = name.lower()
        for key, value in self.tags:
            if key == name:
                return value
        for key, value in self.tags:
            if key.lower() == lowered:
                return value
        return default

    @property
    def result(self) -> str:
        return normalize_pgn_result(self.tag("Result", "*"))

    @property
    def white(self) -> str:
        return self.tag("White", "?") or "?"

    @property
    def black(self) -> str:
        return self.tag("Black", "?") or "?"

    @property
    def event(self) -> str:
        return self.tag("Event", "") or "Chess Core"

    @property
    def date(self) -> str:
        return normalize_pgn_date(self.tag("Date", "????.??.??"))

    def identity(self) -> tuple[str, str, str, str, str]:
        """Stable key for duplicate detection when appending to a database."""
        return (
            self.white,
            self.black,
            self.date,
            self.result,
            _normalize_moves(self.moves),
        )


def chessbase_variant(mode_id: str) -> str | None:
    if mode_id in CHESSBASE_VARIANT:
        return CHESSBASE_VARIANT[mode_id]
    if "+" not in mode_id:
        return None
    tags: list[str] = []
    for token in mode_id.split("+"):
        if token in {"chess", "classic_chess"}:
            continue
        tag = CHESSBASE_VARIANT.get(token)
        if tag and tag not in tags:
            tags.append(tag)
    return "+".join(tags) or None


def normalize_pgn_result(value: str) -> str:
    text = value.strip()
    return _RESULT_ALIASES.get(text, text if text in PGN_RESULTS else "*")


def normalize_pgn_date(value: str) -> str:
    text = value.strip()
    if not text or text in {"?", "??", "????.??.??"}:
        return "????.??.??"
    match = _DATE_YMD.match(text)
    if match is None:
        return text
    year, month, day = match.groups()
    return f"{year}.{int(month):02d}.{int(day):02d}"


def escape_pgn_tag(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def unescape_pgn_tag(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def parse_pgn(text: str) -> tuple[PgnGame, ...]:
    """Split a PGN database (or a Chess Core transcript) into games."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    games: list[PgnGame] = []
    lines = normalized.split("\n")
    index = 0
    while index < len(lines):
        while index < len(lines) and _is_skip_line(lines[index]):
            index += 1
        if index >= len(lines):
            break
        tags: list[tuple[str, str]] = []
        while index < len(lines):
            raw = lines[index]
            if _is_percent_escape(raw):
                index += 1
                continue
            match = _TAG_LINE.match(raw)
            if match is None:
                break
            tags.append((match.group(1), unescape_pgn_tag(match.group(2))))
            index += 1
        move_lines: list[str] = []
        brace_depth = 0
        while index < len(lines):
            raw = lines[index]
            if brace_depth == 0 and _TAG_LINE.match(raw) is not None:
                break
            if _is_percent_escape(raw) and brace_depth == 0:
                index += 1
                continue
            brace_depth += raw.count("{") - raw.count("}")
            if brace_depth < 0:
                brace_depth = 0
            move_lines.append(raw)
            index += 1
        game = _game_from_parts(tags, "\n".join(move_lines))
        if game.tags or game.moves or game.comment:
            games.append(game)
    return tuple(games)


def format_pgn_game(game: PgnGame, *, wrap: int = 80) -> str:
    """One game as PGN text (LF). ChessBase 16 needs STR tags and a trailing result."""
    normalized = normalize_pgn_game(game)
    lines = [
        f'[{name} "{escape_pgn_tag(value)}"]' for name, value in normalized.tags
    ]
    lines.append("")
    body = _movetext_with_result(normalized)
    if body:
        lines.append(wrap_pgn_movetext(body, width=wrap))
    return "\n".join(lines).rstrip() + "\n"


def format_pgn_database(games: Sequence[PgnGame], *, wrap: int = 80) -> str:
    """Concatenate games with a blank line between them (PGN database)."""
    if not games:
        return ""
    blocks = [format_pgn_game(game, wrap=wrap).rstrip("\n") for game in games]
    return "\n\n".join(blocks) + "\n"


def normalize_pgn_game(game: PgnGame) -> PgnGame:
    """Fill the Seven Tag Roster and normalize date/result for ChessBase import."""
    result = normalize_pgn_result(game.tag("Result") or _result_from_moves(game.moves) or "*")
    values: dict[str, str] = {name: value for name, value in game.tags}
    roster: list[tuple[str, str]] = []
    for name in SEVEN_TAG_ROSTER:
        raw = values.get(name, "")
        if name == "Result":
            roster.append((name, result))
        elif name == "Date":
            roster.append((name, normalize_pgn_date(raw or _ROSTER_DEFAULTS[name])))
        else:
            roster.append((name, raw.strip() or _ROSTER_DEFAULTS[name]))
    seen = set(SEVEN_TAG_ROSTER)
    extras: list[tuple[str, str]] = []
    for name, value in game.tags:
        if name in seen:
            continue
        seen.add(name)
        extras.append((name, value))
    date = roster[2][1]
    if "EventDate" not in seen and date != "????.??.??":
        extras.insert(0, ("EventDate", date))
        seen.add("EventDate")
    moves, peeled_comment, _peeled_result = _peel_movetext(game.moves)
    comment = game.comment.strip() or peeled_comment
    return PgnGame(tags=tuple(roster + extras), moves=moves, comment=comment)


def merge_pgn_games(
    existing: Sequence[PgnGame],
    extra: Sequence[PgnGame],
    *,
    skip_duplicates: bool = True,
) -> tuple[PgnGame, ...]:
    merged = [normalize_pgn_game(game) for game in existing]
    seen = {game.identity() for game in merged} if skip_duplicates else set()
    for game in extra:
        item = normalize_pgn_game(game)
        if skip_duplicates and item.identity() in seen:
            continue
        merged.append(item)
        seen.add(item.identity())
    return tuple(merged)


def wrap_pgn_movetext(text: str, *, width: int = 80) -> str:
    """Wrap movetext near ``width`` characters without splitting `{comments}`."""
    tokens = _tokenize_movetext(text)
    if not tokens:
        return ""
    lines: list[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        candidate = f"{current} {token}"
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        current = token
    lines.append(current)
    return "\n".join(lines)


def pgn_game_from_tags(
    tags: Mapping[str, str] | Iterable[tuple[str, str]],
    moves: str,
    *,
    comment: str = "",
) -> PgnGame:
    if isinstance(tags, Mapping):
        items = tuple(tags.items())
    else:
        items = tuple(tags)
    return normalize_pgn_game(PgnGame(tags=items, moves=moves, comment=comment))


def _game_from_parts(tags: Sequence[tuple[str, str]], raw_moves: str) -> PgnGame:
    moves, comment, result = _peel_movetext(raw_moves)
    tag_items = list(tags)
    if result and not _tag_value(tag_items, "Result"):
        tag_items.append(("Result", result))
    elif result:
        tag_items = [
            (name, result if name == "Result" else value) for name, value in tag_items
        ]
    if comment and not _tag_value(tag_items, "Termination"):
        tag_items.append(("Termination", comment))
    return PgnGame(tags=tuple(tag_items), moves=moves, comment=comment)


def _peel_movetext(raw: str) -> tuple[str, str, str]:
    """Return (moves, trailing comment, result) from transcript or PGN movetext."""
    lines = [line.rstrip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    comment = ""
    result = ""
    if lines:
        last = lines[-1].strip()
        aliased = _RESULT_ALIASES.get(last)
        if aliased is not None:
            result = aliased
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
        elif (
            len(lines) >= 2
            and not last.startswith("[")
            and _RESULT_ALIASES.get(lines[-2].strip()) is not None
        ):
            comment = last
            result = _RESULT_ALIASES[lines[-2].strip()]
            lines.pop()
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
    blob = " ".join(line.strip() for line in lines if line.strip())
    moves, inline_comment, inline_result = _split_inline_result(blob)
    if inline_result:
        result = inline_result
    if inline_comment and not comment:
        comment = inline_comment
    if not result:
        result = _result_from_moves(moves)
    return _normalize_moves(moves), comment, result


def _split_inline_result(text: str) -> tuple[str, str, str]:
    tokens = _tokenize_movetext(text)
    result = ""
    comment = ""
    if tokens and tokens[-1] in _RESULT_ALIASES:
        result = _RESULT_ALIASES[tokens.pop()]
    if tokens and tokens[-1].startswith("{") and tokens[-1].endswith("}"):
        comment = tokens[-1][1:-1].strip()
        tokens.pop()
    return " ".join(tokens), comment, result


def _result_from_moves(moves: str) -> str:
    tokens = _tokenize_movetext(moves)
    if tokens and tokens[-1] in _RESULT_ALIASES:
        return _RESULT_ALIASES[tokens[-1]]
    return ""


def _movetext_with_result(game: PgnGame) -> str:
    parts: list[str] = []
    moves = _normalize_moves(game.moves)
    if moves:
        parts.append(moves)
    comment = game.comment.strip()
    if comment:
        parts.append("{" + _sanitize_comment(comment) + "}")
    parts.append(game.result)
    return " ".join(parts)


def _sanitize_comment(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").strip()


def _tokenize_movetext(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index].isspace():
            index += 1
        if index >= length:
            break
        if text[index] == "{":
            end = text.find("}", index)
            if end < 0:
                tokens.append(text[index:].strip())
                break
            tokens.append(text[index : end + 1])
            index = end + 1
            continue
        start = index
        while index < length and not text[index].isspace() and text[index] != "{":
            index += 1
        tokens.append(text[start:index])
    return tokens


def _normalize_moves(text: str) -> str:
    return " ".join(_tokenize_movetext(text))


def _tag_value(tags: Sequence[tuple[str, str]], name: str) -> str:
    for key, value in tags:
        if key == name:
            return value
    return ""


def _is_skip_line(line: str) -> bool:
    stripped = line.strip()
    return not stripped or _is_percent_escape(line)


def _is_percent_escape(line: str) -> bool:
    return line.startswith("%")
