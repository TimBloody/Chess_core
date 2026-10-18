"""Keep the ink string and a separate Latin fold used only for exact match.

Cyrillic piece letters are mapped. Latin C is not rewritten to B: that pair
is ambiguous without the cell. Castling zeros fold the same way as metrics.
"""

from __future__ import annotations

_CASTLE = {
    "0-0": "O-O",
    "0-0-0": "O-O-O",
    "O-O": "O-O",
    "O-O-O": "O-O-O",
    "OO": "O-O",
    "OOO": "O-O-O",
    "ОО": "O-O",
    "ООО": "O-O-O",
}

_LETTER = {
    "К": "N",
    "к": "N",
    "С": "B",
    "Л": "R",
    "л": "R",
    "Ф": "Q",
    "ф": "Q",
    "а": "a",
    "с": "c",
    "е": "e",
    "х": "x",
}


def original_ink(text: str) -> str:
    return "".join(str(text).split())


def normalize_move_text(text: str) -> str:
    """Russian algebraic and castling zeros → Latin SAN. Original is not replaced."""

    raw = original_ink(text).replace("—", "-").replace("–", "-")
    if raw in _CASTLE:
        return _CASTLE[raw]
    out: list[str] = []
    index = 0
    while index < len(raw):
        if raw.startswith("Кр", index) or raw.startswith("кр", index):
            out.append("K")
            index += 2
            continue
        char = raw[index]
        out.append(_LETTER.get(char, char))
        index += 1
    folded = "".join(out)
    return _CASTLE.get(folded, folded)
