"""Role alphabet for scoresheet glyphs. One role = one chess slot, not a Unicode letter.

``accepted_glyphs`` here is the only map from ink to a class: training, decode,
and labels.json v2 all read this table. ``Кр`` is two glyphs (KN then ER).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from chess_core.ocr.hypothesis import MISSING_MOVE

# Latin B (bishop) and latin b (file) are different code points — not an overlap.
# They are visually close; measure BS↔f_b, do not merge.
# Latin c is the file (f_c). Latin C and Cyrillic С/с are bishop (BS).
# That removes the old two-class C/c bishop split: lowercase c is the file slot.


@dataclass(frozen=True, slots=True)
class Role:
    id: str
    canonical: str
    accepted_glyphs: tuple[str, ...]
    kind: str
    index: int


def _role(
    index: int,
    role_id: str,
    canonical: str,
    glyphs: str,
    kind: str,
) -> Role:
    return Role(role_id, canonical, tuple(glyphs), kind, index)


ROLES: tuple[Role, ...] = (
    _role(0, "f_a", "a", "aAаА", "file"),
    _role(1, "f_b", "b", "bбБ", "file"),
    _role(2, "f_c", "c", "c", "file"),
    _role(3, "f_d", "d", "dDдД", "file"),
    _role(4, "f_e", "e", "eEеЕ", "file"),
    _role(5, "f_f", "f", "fF", "file"),
    _role(6, "f_g", "g", "gGгГ", "file"),
    _role(7, "f_h", "h", "hH", "file"),
    _role(8, "r_1", "1", "1", "rank"),
    _role(9, "r_2", "2", "2", "rank"),
    _role(10, "r_3", "3", "3", "rank"),
    _role(11, "r_4", "4", "4", "rank"),
    _role(12, "r_5", "5", "5", "rank"),
    _role(13, "r_6", "6", "6", "rank"),
    _role(14, "r_7", "7", "7", "rank"),
    _role(15, "r_8", "8", "8", "rank"),
    _role(16, "KN", "N", "NnКкKk", "piece"),
    _role(17, "BS", "C", "CСсB", "piece"),
    _role(18, "RK", "R", "RrЛл", "piece"),
    _role(19, "QN", "Q", "QqФф", "piece"),
    _role(20, "ER", "р", "рР", "piece"),
    _role(21, "X", "x", "xXхХ", "marker"),
    _role(22, "O", "o", "Oo0Оо", "marker"),
    _role(23, "PLUS", "+", "+", "marker"),
    _role(24, "HASH", "#", "#", "marker"),
    _role(25, "EQ", "=", "=", "marker"),
)

ROLE_IDS: tuple[str, ...] = tuple(role.id for role in ROLES)
ROLE_BY_ID: dict[str, Role] = {role.id: role for role in ROLES}
N_ROLES = len(ROLES)

_GLYPH_TO_ROLE: dict[str, str] = {}
for _role_row in ROLES:
    for _glyph in _role_row.accepted_glyphs:
        if _glyph in _GLYPH_TO_ROLE and _GLYPH_TO_ROLE[_glyph] != _role_row.id:
            raise RuntimeError(
                f"глиф {_glyph!r} в двух ролях: {_GLYPH_TO_ROLE[_glyph]} и {_role_row.id}"
            )
        _GLYPH_TO_ROLE[_glyph] = _role_row.id

# b/B: file keeps b/б/Б, bishop keeps latin B. Same ink family, different code points.
KNOWN_VISUAL_NEAR_MISSES: tuple[tuple[str, str], ...] = (("f_b", "BS"), ("f_c", "BS"))

PIECE_ROLES: frozenset[str] = frozenset({"KN", "BS", "RK", "QN"})
FILE_ROLES: frozenset[str] = frozenset(role.id for role in ROLES if role.kind == "file")
RANK_ROLES: frozenset[str] = frozenset(role.id for role in ROLES if role.kind == "rank")

_SAN_PIECE = {"KN": "N", "BS": "B", "RK": "R", "QN": "Q"}
_RU_PIECE = {"KN": "К", "BS": "С", "RK": "Л", "QN": "Ф"}


def canonicalize(char: str) -> str:
    """Map one ink glyph to a role id."""

    if len(char) != 1:
        raise ValueError(f"ожидался один глиф, получено {char!r}")
    role_id = _GLYPH_TO_ROLE.get(char)
    if role_id is None:
        raise ValueError(f"неизвестная роль для глифа {char!r}")
    return role_id


def try_canonicalize(char: str) -> str | None:
    if len(char) != 1:
        return None
    return _GLYPH_TO_ROLE.get(char)


def role_to_canonical(role_id: str) -> str:
    return ROLE_BY_ID[role_id].canonical


def restore_case(role_id: str, position: str) -> str:
    """Render a role as a SAN character given its slot in the token."""

    role = ROLE_BY_ID[role_id]
    if position == "file":
        if role_id == "BS":
            return "c"
        return role.canonical.lower() if role.kind == "file" else role.canonical
    if position == "rank":
        return role.canonical
    if position in {"piece", "promo"}:
        if role_id == "KN":
            return "N"
        if role_id == "BS":
            return "B"
        if role_id == "RK":
            return "R"
        if role_id == "QN":
            return "Q"
        if role_id == "ER":
            return "р"
        return role.canonical.upper() if role.canonical.isalpha() else role.canonical
    if position == "castle":
        return "O"
    if position == "capture":
        return "x"
    if position == "check":
        return role.canonical
    return role.canonical


def _piece_san(role_id: str, *, notation_mode: str, king: bool) -> str:
    if king:
        return "K"
    if role_id == "KN":
        return "K" if notation_mode == "en" else "N"
    return _SAN_PIECE.get(role_id, ROLE_BY_ID[role_id].canonical)


def format_ru(san: str) -> str:
    """Latin SAN → Russian algebraic for UI. King is Кр, knight is К."""

    if san in {"O-O", "0-0", "OO"}:
        return "0-0"
    if san in {"O-O-O", "0-0-0", "OOO"}:
        return "0-0-0"
    out = []
    i = 0
    if san.startswith("K"):
        out.append("Кр")
        i = 1
    mapping = {"N": "К", "B": "С", "R": "Л", "Q": "Ф"}
    while i < len(san):
        char = san[i]
        out.append(mapping.get(char, char))
        i += 1
    return "".join(out)


def roles_to_san(roles: Sequence[str], *, notation_mode: str = "ru") -> str:
    """Assemble a cell token from CNN role ids. Never empty."""

    sequence = [item for item in roles if item in ROLE_BY_ID]
    if not sequence:
        return MISSING_MOVE
    castle = _castle_san(sequence)
    if castle is not None:
        return castle

    index = 0
    king = False
    piece = ""
    if (
        index + 1 < len(sequence)
        and sequence[index] == "KN"
        and sequence[index + 1] == "ER"
    ):
        king = True
        piece = "K"
        index += 2
    elif sequence[index] in PIECE_ROLES:
        piece = _piece_san(sequence[index], notation_mode=notation_mode, king=False)
        index += 1

    from_file = ""
    to_file = ""
    rank = ""
    capture = False
    promo = ""
    suffix = ""

    def take_file() -> str:
        nonlocal index
        if index >= len(sequence):
            return ""
        role_id = sequence[index]
        if role_id in FILE_ROLES or role_id == "BS":
            glyph = restore_case(role_id, "file")
            index += 1
            return glyph
        return ""

    def take_rank() -> str:
        nonlocal index
        if index >= len(sequence):
            return ""
        role_id = sequence[index]
        if role_id in RANK_ROLES:
            index += 1
            return ROLE_BY_ID[role_id].canonical
        return ""

    peek = sequence[index] if index < len(sequence) else ""
    if peek == "X":
        capture = True
        index += 1
        to_file = take_file()
        rank = take_rank()
    elif peek in FILE_ROLES or peek == "BS":
        first = take_file()
        if index < len(sequence) and sequence[index] == "X":
            from_file = first
            capture = True
            index += 1
            to_file = take_file()
            rank = take_rank()
        elif index < len(sequence) and sequence[index] in FILE_ROLES:
            from_file = first
            to_file = take_file()
            rank = take_rank()
        else:
            to_file = first
            rank = take_rank()
    else:
        rank = take_rank()

    if index < len(sequence) and sequence[index] == "EQ":
        index += 1
        if index < len(sequence) and sequence[index] in PIECE_ROLES:
            promo = "=" + _piece_san(sequence[index], notation_mode="en", king=False)
            index += 1
        else:
            promo = "="
    while index < len(sequence) and sequence[index] in {"PLUS", "HASH"}:
        suffix += ROLE_BY_ID[sequence[index]].canonical
        index += 1
    if index < len(sequence):
        rest = "".join(restore_case(item, "piece") for item in sequence[index:])
        suffix += rest

    body = piece + from_file + ("x" if capture else "") + to_file + rank + promo + suffix
    return body if body else MISSING_MOVE


def _castle_san(sequence: Sequence[str]) -> str | None:
    """[O] [O] (separator?) [O]?. Separators are leftover HASH/PLUS/X/EQ, not a dash class."""

    if not sequence or sequence[0] != "O":
        return None
    o_count = 0
    for role_id in sequence:
        if role_id == "O":
            o_count += 1
            continue
        if role_id in PIECE_ROLES or role_id in FILE_ROLES or role_id in RANK_ROLES or role_id == "ER":
            return None
    if o_count >= 3:
        return "O-O-O"
    if o_count == 2:
        return "O-O"
    if o_count == 1 and len(sequence) == 1:
        return "O"
    return None


def split_kr(roles: Sequence[str]) -> tuple[str, ...]:
    """``Кр`` / king = KN + ER. Inverse of the two-glyph rule."""

    out: list[str] = []
    index = 0
    while index < len(roles):
        if (
            index + 1 < len(roles)
            and roles[index] == "KN"
            and roles[index + 1] == "ER"
        ):
            out.append("KN+ER")
            index += 2
            continue
        out.append(roles[index])
        index += 1
    return tuple(out)


def kr_roles() -> tuple[str, str]:
    return ("KN", "ER")


def serialize_roles(roles: Sequence[str]) -> str:
    return " ".join(roles)


def parse_roles(token: str) -> tuple[str, ...]:
    return tuple(part for part in token.split() if part)


def glyphs_to_san(chars: Sequence[str], *, notation_mode: str = "ru") -> str:
    """Ink characters → SAN. Hyphens are separators, not a class."""

    roles: list[str] = []
    for char in chars:
        if char in {"-", "–", "—", " ", "_"}:
            continue
        role_id = try_canonicalize(char)
        if role_id is None:
            continue
        roles.append(role_id)
    return roles_to_san(roles, notation_mode=notation_mode)


def hypothesize_notation(role_ids: Sequence[str]) -> dict[str, object]:
    """Guess ru vs en from ER (the second letter of «Кр»). Never apply this blindly."""

    er = sum(1 for role_id in role_ids if role_id == "ER")
    if er:
        guess = "ru"
        reason = f"роль ER встретилась {er} раз (вторая буква «Кр»)"
    else:
        guess = "en"
        reason = "роли ER нет; латиница вероятнее, но без --notation не применяем"
    return {
        "notation_mode_hypothesis": guess,
        "reason": reason,
        "applied": False,
        "er_count": er,
    }


def chars_to_roles(chars: Iterable[str]) -> tuple[str, ...]:
    return tuple(canonicalize(char) for char in chars)


def labels_v2_payload() -> dict[str, object]:
    return {
        "version": 2,
        "roles": [
            {
                "id": role.id,
                "canonical": role.canonical,
                "accepted_glyphs": list(role.accepted_glyphs),
                "kind": role.kind,
                "index": role.index,
            }
            for role in ROLES
        ],
    }


OLD_CHAR_TO_ROLE: dict[str, str] = {
    "a": "f_a",
    "b": "f_b",
    "c": "f_c",
    "d": "f_d",
    "e": "f_e",
    "f": "f_f",
    "g": "f_g",
    "h": "f_h",
    "N": "KN",
    "K": "KN",
    "B": "BS",
    "R": "RK",
    "Q": "QN",
    "x": "X",
    "O": "O",
    "1": "r_1",
    "2": "r_2",
    "3": "r_3",
    "4": "r_4",
    "5": "r_5",
    "6": "r_6",
    "7": "r_7",
    "8": "r_8",
    "#": "HASH",
    "C": "BS",
    "Л": "RK",
    "Ф": "QN",
    "р": "ER",
}


def migrate_v1_charset(charset: Sequence[str]) -> tuple[dict[int, str], list[str]]:
    """Old class index → new role id. Warnings for irreversible merges."""

    mapping: dict[int, str] = {}
    warnings: list[str] = []
    seen_roles: dict[str, list[str]] = {}
    for index, old in enumerate(charset):
        role_id = OLD_CHAR_TO_ROLE.get(old)
        if role_id is None:
            try:
                role_id = canonicalize(old)
            except ValueError:
                warnings.append(f"старый класс {old!r} (index {index}) не отображается ни на одну роль")
                continue
        mapping[index] = role_id
        seen_roles.setdefault(role_id, []).append(old)
    if "c" in charset and "C" not in charset:
        warnings.append(
            "C и c уже были слиты в старом charset (класс 'c'); "
            "разделить обратно нельзя — 'c' → f_c, верхний C в этом файле отсутствовал"
        )
    for role_id, olds in seen_roles.items():
        if len(olds) > 1:
            warnings.append(f"роль {role_id} собрана из старых классов {olds}")
    return mapping, warnings
