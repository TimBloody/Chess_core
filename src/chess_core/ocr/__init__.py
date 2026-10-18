"""Scoresheet OCR domain: gold, metrics, decode hypotheses.

Pipeline orchestration stays in ``app.experiments``. This package has no UI
and does not import ``app``.
"""

from chess_core.ocr.gold import GoldSheet, gold_dir, load_gold
from chess_core.ocr.hypothesis import MISSING_MOVE, CellHypothesis
from chess_core.ocr.metrics import SheetMetrics, glyph_confusion, sheet_metrics

__all__ = [
    "CellHypothesis",
    "GoldSheet",
    "MISSING_MOVE",
    "SheetMetrics",
    "glyph_confusion",
    "gold_dir",
    "load_gold",
    "sheet_metrics",
]
