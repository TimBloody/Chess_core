"""P5.0 ruler: real glyphs agree with gold, and the spec bar is not quietly lowered."""

from __future__ import annotations

import json

import pytest

from chess_core.ocr.glyph_eval import evaluate_predictions, roc_auc
from chess_core.ocr.gold import gold_dir, load_gold
from chess_core.ocr.roles import N_ROLES, try_canonicalize


def test_roc_auc_perfect_and_useless() -> None:
    assert roc_auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert roc_auc([0.2, 0.1, 0.9, 0.8], [1, 1, 0, 0]) == 0.0


def test_evaluate_counts_top5_miss() -> None:
    metrics = evaluate_predictions(
        ["f_c", "r_4"],
        [("KN", "f_a"), ("r_4", "r_2")],
        [0.95, 0.4],
    )
    assert metrics["per_glyph_top1"] == 0.5
    assert metrics["per_glyph_top5"] == 0.5
    assert metrics["confident_wrong_gt_0.9"] == 1
    assert len(metrics["confusion"]) == N_ROLES


def test_real_glyphs_match_gold_chars() -> None:
    path = gold_dir() / "glyphs_real.json"
    if not path.is_file():
        pytest.skip("нет data/gold/glyphs_real.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    glyphs = payload["glyphs"]
    by_cell: dict[tuple[str, str], list[dict]] = {}
    for row in glyphs:
        assert try_canonicalize(str(row["char"])) == row["role"]
        by_cell.setdefault((str(row["sheet_id"]), str(row["cell"])), []).append(row)
    for (sheet_id, _cell), group in by_cell.items():
        gold = load_gold(sheet_id)
        assert gold is not None
        group.sort(key=lambda item: int(item["glyph_index"]))
        cell_index = int(group[0]["cell_index"])
        chars = gold.chars[cell_index]
        assert [item["char"] for item in group] == list(chars)
        assert len(group) == len(chars)


def test_real_glyph_count_meets_spec() -> None:
    """Spec bar is 70. Do not edit this number down to the observed count."""

    path = gold_dir() / "glyphs_real.json"
    if not path.is_file():
        pytest.skip("нет data/gold/glyphs_real.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert int(payload["n"]) >= 70
