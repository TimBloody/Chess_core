"""Ground-truth dump from the neighbour OCR example sheets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from chess_core.app.experiments.ocr_language import levenshtein, normalize_read
from chess_core.app.experiments.ocr_stage12 import ocr_project_root

_CELL_NAME = re.compile(r"(?P<order>\d+)_r(?P<row>\d+)_c(?P<col>\d+)", re.I)


@dataclass(frozen=True, slots=True)
class SheetTruth:
    source: Path
    moves: tuple[str, ...]
    char_texts: tuple[tuple[str, ...], ...]
    path: Path


def parse_cell_name(name: str) -> tuple[int, int, int] | None:
    match = _CELL_NAME.search(name)
    if match is None:
        return None
    return int(match["order"]), int(match["row"]), int(match["col"])


def load_sheet_truth(image: Path) -> SheetTruth | None:
    from chess_core.ocr.gold import load_gold

    gold = load_gold(image)
    if gold is not None:
        return SheetTruth(
            source=image,
            moves=gold.plies,
            char_texts=gold.chars,
            path=gold.path,
        )
    root = ocr_project_root()
    if root is None:
        return None
    path = root / "data" / "examples" / f"sheet_{image.stem}" / "moves.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    cells = list(data.get("cells") or [])
    cells.sort(key=lambda row: int(row.get("order_index") or 0))
    top = tuple(str(item) for item in (data.get("moves") or ()) if str(item))
    cell_moves = tuple(str(row.get("move_text") or "") for row in cells if row.get("move_text"))
    moves = top or cell_moves
    chars = tuple(
        tuple(str(item) for item in (row.get("char_texts") or ()))
        for row in cells
        if row.get("move_text")
    )
    return SheetTruth(source=image, moves=moves, char_texts=chars, path=path)


def cell_metrics(
    raws: tuple[str, ...],
    legal: tuple[str, ...],
    truth: SheetTruth | None,
) -> dict[str, object]:
    if truth is None:
        return {"ground_truth": None}
    n = min(len(truth.moves), len(raws), len(legal))
    raw_exact = sum(1 for i in range(n) if normalize_read(raws[i]) == truth.moves[i])
    legal_exact = sum(1 for i in range(n) if legal[i] == truth.moves[i])
    cer = 0.0
    for i in range(n):
        gold = truth.moves[i]
        pred = normalize_read(raws[i])
        cer += levenshtein(pred, gold) / max(len(gold), 1)
    return {
        "ground_truth": str(truth.path),
        "n_truth": len(truth.moves),
        "n_compared": n,
        "raw_exact": raw_exact,
        "raw_exact_frac": raw_exact / max(n, 1),
        "legal_exact": legal_exact,
        "legal_exact_frac": legal_exact / max(n, 1),
        "mean_cer": cer / max(n, 1),
        "truth_moves": list(truth.moves),
        "missing_charset": ["+", "=", "O-O as two O glyphs, not a class"],
    }
