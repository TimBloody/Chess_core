"""Non-destructive merge/split suspicions. Never rewrite MSER boxes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class SegSuspicion:
    seg_flag: str | None
    seg_confidence: float
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "seg_flag": self.seg_flag,
            "seg_confidence": self.seg_confidence,
            "notes": self.notes,
        }


def inspect_cell_glyphs(glyphs: Sequence[Any]) -> list[SegSuspicion]:
    if not glyphs:
        return []
    widths = [glyph.box.width for glyph in glyphs]
    heights = [glyph.box.height for glyph in glyphs]
    median_w = float(np.median(widths))
    median_h = float(np.median(heights)) or 1.0
    out: list[SegSuspicion] = []
    boxes = list(glyphs)
    for index, glyph in enumerate(boxes):
        flag = None
        conf = 0.0
        notes = ""
        if glyph.box.width > median_w * 1.7 and glyph.box.height <= median_h * 1.35:
            minima = _vertical_minima(glyph.mnist)
            if len(minima) >= 2:
                flag = "merge_suspected"
                conf = min(1.0, glyph.box.width / (median_w * 2.2))
                notes = f"wide bbox minima={len(minima)}"
        if index + 1 < len(boxes):
            nxt = boxes[index + 1]
            gap = nxt.box.x1 - glyph.box.x2
            overlap = _vertical_overlap(glyph.box.y1, glyph.box.y2, nxt.box.y1, nxt.box.y2)
            if gap >= 0 and gap < 0.15 * median_h and overlap > 0.70:
                flag = "split_suspected"
                conf = overlap
                notes = f"gap={gap} overlap={overlap:.2f}"
        out.append(SegSuspicion(flag, float(conf), notes))
    return out


def _vertical_minima(tile: np.ndarray) -> list[int]:
    gray = np.asarray(tile)
    if gray.ndim == 3:
        gray = gray[..., 0]
    ink = (gray < 175).astype(np.uint8)
    if ink.size == 0:
        return []
    col = np.sum(ink, axis=0, dtype=np.float64)
    if col.size < 6:
        return []
    mean = float(col.mean())
    hits = []
    for x in range(2, col.size - 2):
        if col[x] < col[x - 1] and col[x] < col[x + 1] and col[x] < 0.45 * mean:
            hits.append(x)
    return hits


def flag_hits_against_gold(
    details: Sequence[Any],
    gold_chars: Sequence[Sequence[str]],
) -> dict[str, float | int]:
    """How often merge/split flags agree with gold glyph counts. No MSER rewrite."""

    n = min(len(details), len(gold_chars))
    merge_flags = split_flags = merge_ok = split_ok = 0
    for i in range(n):
        row = details[i]
        n_gold = len(gold_chars[i])
        n_pred = int(row.get("n_glyphs") or 0)
        flag = row.get("seg_flag")
        if flag == "merge_suspected":
            merge_flags += 1
            if n_pred < n_gold:
                merge_ok += 1
        elif flag == "split_suspected":
            split_flags += 1
            if n_pred > n_gold:
                split_ok += 1
    return {
        "merge_flags": merge_flags,
        "split_flags": split_flags,
        "merge_true": merge_ok,
        "split_true": split_ok,
        "flag_precision": (merge_ok + split_ok) / max(merge_flags + split_flags, 1),
    }


def _vertical_overlap(a1: int, a2: int, b1: int, b2: int) -> float:
    inter = max(0, min(a2, b2) - max(a1, b1))
    denom = max(min(a2 - a1, b2 - b1), 1)
    return inter / denom
