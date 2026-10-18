"""P5.0b: manual labels exist, the ladder did not train, EMNIST control holds."""

from __future__ import annotations

import json
from pathlib import Path

from chess_core.infra.paths import project_root
from chess_core.ocr.diag_stats import proportion, wilson_interval
from chess_core.ocr.gold import gold_dir


def test_wilson_is_deterministic() -> None:
    assert wilson_interval(8, 59) == wilson_interval(8, 59)
    block = proportion(8, 59)
    assert block["ci95_lo"] < block["p"] < block["ci95_hi"]


def test_manual_labels_cover_every_crop() -> None:
    payload = json.loads((gold_dir() / "glyphs_real_manual.json").read_text(encoding="utf-8"))
    rows = payload["glyphs"]
    assert rows
    for row in rows:
        path = project_root() / str(row["path"])
        assert path.is_file(), row["path"]
        assert row.get("manual_role") or row.get("manual_ok") is False


def test_ladder_did_not_train_on_real_crops() -> None:
    report = json.loads(
        (project_root() / "output" / "ocr_runs" / "p5_diag" / "report.json").read_text(encoding="utf-8")
    )
    assert report["trained_epochs"] == 0
    assert report["real_crops_used_as_training_labels"] is False
    assert report["hand_c_allowed"] is False
    source = (project_root() / "src" / "chess_core" / "tools" / "audit_p5_diag.py").read_text(encoding="utf-8")
    assert "train_glyph_cnn" not in source
    assert ".fit(" not in source


def test_emnist_control_still_holds() -> None:
    report = json.loads(
        (project_root() / "output" / "ocr_runs" / "p5_diag" / "report.json").read_text(encoding="utf-8")
    )
    top1 = report["ladder"]["B0"]["top1"]
    assert top1["n"] == 2000
    assert top1["p"] >= 0.95
    assert top1["ci95_hi"] >= 0.97
    assert abs(top1["hits"] / top1["n"] - top1["p"]) < 1e-12


def test_sheet_coverage_unchanged() -> None:
    root = project_root() / "output" / "ocr_runs"
    for sheet in ("image_0006", "image_0552"):
        report = json.loads((root / f"{sheet}_cnn" / "report.json").read_text(encoding="utf-8"))
        assert report["metrics"]["coverage"] == 1.0
