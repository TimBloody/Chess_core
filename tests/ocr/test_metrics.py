"""P0 metrics and gold loader."""

from __future__ import annotations

from chess_core.ocr.gold import load_gold
from chess_core.ocr.hypothesis import MISSING_MOVE, CellHypothesis
from chess_core.ocr.metrics import coverage_rate, glyph_confusion, sheet_metrics


def test_gold_0006_has_24_plies() -> None:
    gold = load_gold("image_0006")
    assert gold is not None
    assert gold.plies[:4] == ("c4", "c6", "Nc3", "g5")
    assert len(gold.plies) == 24
    assert len(gold.chars) == 24


def test_gold_0552_prefix_is_legal_length() -> None:
    gold = load_gold("image_0552")
    assert gold is not None
    assert gold.plies[:4] == ("d4", "d5", "c4", "e6")
    assert gold.plies[14] == "O-O"
    assert gold.ambiguous is True
    assert gold.notes
    assert len(gold.plies) >= 16


def test_coverage_is_one_when_nothing_empty() -> None:
    assert coverage_rate(("c4", "?", "Nf3")) == 1.0
    assert coverage_rate(("", "c4")) == 0.5


def test_sheet_metrics_never_treats_question_as_empty() -> None:
    gold = load_gold("image_0006")
    assert gold is not None
    raws = ("c4", "xx")
    hyps = (
        CellHypothesis("c4", "c4", True, False, "legal_exact", "legal"),
        CellHypothesis(MISSING_MOVE, "", False, True, "no_legal_match", "raw_fallback"),
    )
    measured = sheet_metrics(sheet_id="image_0006", gold=gold, raws=raws, hypotheses=hyps)
    assert measured.coverage == 1.0
    assert measured.raw_move_acc == 0.5
    assert measured.legal_move_acc == 0.5


def test_confusion_counts_alignments() -> None:
    table = glyph_confusion((("c", "4"), ("N", "c", "3")), (("c", "#"), ("N", "e", "3")))
    assert table["c"]["c"] == 1
    assert table["4"]["#"] == 1
    assert table["c"]["e"] == 1
