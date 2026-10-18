"""Sheet-level OCR metrics against data/gold. ECE is filled in P6."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence

from chess_core.ocr.gold import GoldSheet
from chess_core.ocr.hypothesis import CellHypothesis
from chess_core.ocr.roles import ROLE_IDS, try_canonicalize


@dataclass(frozen=True, slots=True)
class SheetMetrics:
    sheet_id: str
    n_occupied: int
    n_gold: int
    n_compared: int
    raw_move_acc: float
    legal_move_acc: float
    coverage: float
    glyph_conf_mean: float | None
    glyph_conf_median: float | None
    seg_err_rate: float | None
    ece: float | None
    raw_exact: int
    legal_exact: int
    n_legal_flags: int
    n_low_confidence: int
    extra: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheet_id": self.sheet_id,
            "n_occupied": self.n_occupied,
            "n_gold": self.n_gold,
            "n_compared": self.n_compared,
            "raw_move_acc": self.raw_move_acc,
            "legal_move_acc": self.legal_move_acc,
            "coverage": self.coverage,
            "glyph_conf": {
                "mean": self.glyph_conf_mean,
                "median": self.glyph_conf_median,
            },
            "seg_err_rate": self.seg_err_rate,
            "ece": self.ece,
            "raw_exact": self.raw_exact,
            "legal_exact": self.legal_exact,
            "n_legal_flags": self.n_legal_flags,
            "n_low_confidence": self.n_low_confidence,
            **self.extra,
        }


def _norm(text: str) -> str:
    return "".join(text.split())


def _castle_fold(text: str) -> str:
    folded = _norm(text)
    mapping = {
        "0-0": "O-O",
        "0-0-0": "O-O-O",
        "OO": "O-O",
        "OOO": "O-O-O",
        "Kg1": "O-O",
        "Kg8": "O-O",
        "Kc1": "O-O-O",
        "Kc8": "O-O-O",
    }
    return mapping.get(folded, folded)


def coverage_rate(texts: Sequence[str]) -> float:
    if not texts:
        return 1.0
    return sum(1 for text in texts if text) / len(texts)


def sheet_metrics(
    *,
    sheet_id: str,
    gold: GoldSheet | None,
    raws: Sequence[str],
    hypotheses: Sequence[CellHypothesis],
    cell_details: Sequence[Mapping[str, Any]] = (),
    glyph_scores: Sequence[float] = (),
) -> SheetMetrics:
    occupied = len(raws)
    texts = tuple(item.text for item in hypotheses)
    if len(texts) != occupied:
        raise ValueError("hypotheses and raws must cover the same occupied cells")
    cover = coverage_rate(texts)
    gold_plies = gold.plies if gold is not None else ()
    n_gold = len(gold_plies)
    n = min(n_gold, occupied, len(hypotheses))
    raw_exact = sum(
        1 for i in range(n) if _castle_fold(raws[i]) == _castle_fold(gold_plies[i])
    )
    legal_exact = sum(
        1
        for i in range(n)
        if _castle_fold(hypotheses[i].text) == _castle_fold(gold_plies[i])
    )
    n_legal = sum(1 for item in hypotheses[:n] if item.legal)
    scores = [float(value) for value in glyph_scores]
    if not scores:
        scores = [
            float(glyph["score"])
            for row in cell_details
            for glyph in row.get("glyphs") or ()
            if "score" in glyph
        ]
    mean_conf = (sum(scores) / len(scores)) if scores else None
    median_conf = statistics.median(scores) if scores else None
    mismatches = 0
    counted = 0
    for row in cell_details:
        expected = row.get("expected_glyphs")
        n_glyphs = row.get("n_glyphs")
        if expected is None or n_glyphs is None:
            continue
        counted += 1
        if int(n_glyphs) != int(expected):
            mismatches += 1
    seg_err = (mismatches / counted) if counted else None
    return SheetMetrics(
        sheet_id=sheet_id,
        n_occupied=occupied,
        n_gold=n_gold,
        n_compared=n,
        raw_move_acc=raw_exact / n if n else 0.0,
        legal_move_acc=n_legal / n if n else 0.0,
        coverage=cover,
        glyph_conf_mean=mean_conf,
        glyph_conf_median=median_conf,
        seg_err_rate=seg_err,
        ece=None,
        raw_exact=raw_exact,
        legal_exact=legal_exact,
        n_legal_flags=n_legal,
        n_low_confidence=sum(1 for item in hypotheses if item.low_confidence),
        extra={
            "gold_path": str(gold.path) if gold is not None else None,
            "truth_moves": list(gold_plies),
            "empty_legal": sum(1 for text in texts if not text),
            "ambiguous_gold": bool(gold.ambiguous) if gold is not None else False,
        },
    )


def glyph_confusion(
    gold_chars: Sequence[Sequence[str]],
    pred_chars: Sequence[Sequence[str]],
) -> dict[str, dict[str, int]]:
    table: dict[str, Counter[str]] = defaultdict(Counter)
    n = min(len(gold_chars), len(pred_chars))
    for i in range(n):
        gold_row = gold_chars[i]
        pred_row = pred_chars[i]
        width = min(len(gold_row), len(pred_row))
        for j in range(width):
            table[gold_row[j]][pred_row[j]] += 1
        if len(gold_row) != len(pred_row):
            table["<len>"][f"{len(gold_row)}->{len(pred_row)}"] += 1
    return {key: dict(value) for key, value in table.items()}


def format_confusion(table: Mapping[str, Mapping[str, int]]) -> str:
    if not table:
        return "confusion: нет посимвольного gold"
    lines = ["confusion (gold → pred:count):"]
    for gold in sorted(table):
        parts = ", ".join(
            f"{pred}:{count}" for pred, count in sorted(table[gold].items(), key=lambda item: (-item[1], item[0]))
        )
        lines.append(f"  {gold} → {parts}")
    return "\n".join(lines)


def write_report(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def pred_chars_from_details(details: Iterable[Mapping[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for cell in details:
        rows.append([str(glyph.get("char") or "") for glyph in cell.get("glyphs") or ()])
    return rows


def gold_chars_to_roles(gold_chars: Sequence[Sequence[str]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for cell in gold_chars:
        mapped: list[str] = []
        for char in cell:
            role_id = try_canonicalize(char)
            if role_id is not None:
                mapped.append(role_id)
        rows.append(mapped)
    return rows


def role_confusion_matrix(
    gold_roles: Sequence[Sequence[str]],
    pred_roles: Sequence[Sequence[str]],
) -> list[list[int]]:
    index = {role_id: i for i, role_id in enumerate(ROLE_IDS)}
    size = len(ROLE_IDS)
    matrix = [[0] * size for _ in range(size)]
    n = min(len(gold_roles), len(pred_roles))
    for i in range(n):
        width = min(len(gold_roles[i]), len(pred_roles[i]))
        for j in range(width):
            gold_id = gold_roles[i][j]
            pred_id = pred_roles[i][j]
            if gold_id not in index or pred_id not in index:
                continue
            matrix[index[gold_id]][index[pred_id]] += 1
    return matrix


def flatten_roles(rows: Sequence[Sequence[str]]) -> list[str]:
    return [role_id for row in rows for role_id in row]


def role_support_counts(role_ids: Sequence[str]) -> dict[str, int]:
    counts = Counter(role_ids)
    return {role_id: int(counts.get(role_id, 0)) for role_id in ROLE_IDS}


def max_class_share(role_ids: Sequence[str]) -> dict[str, Any]:
    if not role_ids:
        return {"role": None, "count": 0, "share": 0.0, "n": 0}
    counts = Counter(role_ids)
    role, count = counts.most_common(1)[0]
    n = len(role_ids)
    return {"role": role, "count": int(count), "share": count / n, "n": n}


def pairs_suspected(matrix: Sequence[Sequence[int]], *, limit: int = 10) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for i, gold_id in enumerate(ROLE_IDS):
        for j, pred_id in enumerate(ROLE_IDS):
            if i == j:
                continue
            count = int(matrix[i][j]) if i < len(matrix) and j < len(matrix[i]) else 0
            if count:
                pairs.append({"gold": gold_id, "pred": pred_id, "n": count})
    pairs.sort(key=lambda row: (-row["n"], row["gold"], row["pred"]))
    return pairs[:limit]


def cyrillic_role_share(role_ids: Sequence[str]) -> dict[str, Any]:
    exclusive = {"ER"}
    n = len(role_ids)
    hits = sum(1 for role_id in role_ids if role_id in exclusive)
    return {
        "exclusive_roles": sorted(exclusive),
        "count": hits,
        "share": (hits / n) if n else 0.0,
        "n": n,
    }


def role_report(
    gold_chars: Sequence[Sequence[str]],
    pred_roles: Sequence[Sequence[str]],
) -> dict[str, Any]:
    gold_roles = gold_chars_to_roles(gold_chars)
    matrix = role_confusion_matrix(gold_roles, pred_roles)
    flat_pred = flatten_roles(pred_roles)
    return {
        "role_ids": list(ROLE_IDS),
        "role_confusion": matrix,
        "role_support": role_support_counts(flat_pred),
        "max_class_share": max_class_share(flat_pred),
        "pairs_suspected": pairs_suspected(matrix),
        "cyrillic_role_share": cyrillic_role_share(flat_pred),
    }
