"""P2 content-gate invariants, leak tests, geometry, asymmetry."""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from chess_core.app.experiments.ocr import run_scoresheet_pipeline
from chess_core.ocr.gate.catalog import (
    assert_holdout_unused_by_fit,
    assert_sheet_disjoint,
    gate_root,
    load_catalog,
)
from chess_core.ocr.gate.content import load_content_gate
from chess_core.ocr.gate.geometry import GeometryPrefilter, SheetGeometry
from chess_core.ocr.gate.integrity import inspect_cell_glyphs
from chess_core.ocr.gate.modes import make_mode
from chess_core.ocr.hypothesis import MISSING_MOVE, CellHypothesis
from chess_core.infra.paths import project_root
from chess_core.tools.collect_gate_crops import EVAL_SHEETS, _read_gray
from chess_core.tools.demo_glyph_ocr import main as demo_main


def test_off_mode_never_rejects() -> None:
    decision = make_mode("off").apply(0.01)
    assert decision.accepted
    assert not decision.skip_cnn
    assert not decision.cell_missing
    assert make_mode("off").emit_p(0.01) == 1.0


def test_soft_and_hard_empty_crop_is_question_not_blank() -> None:
    hypo = CellHypothesis(
        MISSING_MOVE,
        MISSING_MOVE,
        False,
        True,
        "gate_reject",
        "gate",
        gate_rejected=True,
        p_content=0.1,
    )
    assert hypo.text == "?"
    assert hypo.text != ""
    with pytest.raises(ValueError):
        CellHypothesis("", "x", False, True, "bad", "gate")


def test_geometry_marks_index_and_header() -> None:
    geo = SheetGeometry(
        skipped_columns=(0, 3, 6),
        skipped_rows=(0,),
        first_data_row=1,
        grid_rows=21,
        grid_cols=9,
        h_lines=(),
        v_lines=(),
    )
    pre = GeometryPrefilter()
    assert pre.zone(geo, row=2, col=0) == "printed_index"
    assert pre.zone(geo, row=0, col=1) == "printed_header"
    assert pre.zone(geo, row=2, col=1) is None
    blank = np.full((24, 24), 240, dtype=np.uint8)
    soft = load_content_gate("soft")
    hard = load_content_gate("hard")
    off = load_content_gate("off")
    printed = soft.decide_crop(blank, sheet_geometry=geo, row=2, col=0)
    assert printed.source == "geometry"
    assert not printed.accepted
    assert hard.decide_crop(blank, sheet_geometry=geo, row=2, col=0).skip_cnn
    off_d = off.decide_crop(blank, sheet_geometry=geo, row=2, col=0)
    assert off_d.accepted
    assert off_d.p_content == 1.0
    assert not off_d.skip_cnn


def test_catalog_sheet_and_hash_disjoint() -> None:
    rows = load_catalog()
    if not rows:
        pytest.skip("data/gate/labels.json ещё нет")
    assert_sheet_disjoint(rows)
    train_hash = {row.sha256 for row in rows if row.split == "train"}
    hold_hash = {row.sha256 for row in rows if row.split == "holdout"}
    assert train_hash & hold_hash == set()
    fit = gate_root() / "fit_paths.json"
    if fit.is_file():
        used = json.loads(fit.read_text(encoding="utf-8")).get("train_paths") or []
        assert_holdout_unused_by_fit(used, rows)
        hold_paths = {row.path for row in rows if row.split == "holdout"}
        assert not (set(used) & hold_paths)


def test_eval_sheets_absent_from_gate_corpus() -> None:
    rows = load_catalog()
    if not rows:
        pytest.skip("data/gate/labels.json ещё нет")
    sheets = {row.source_sheet for row in rows}
    assert sheets.isdisjoint(EVAL_SHEETS)
    n_pos = sum(1 for row in rows if row.label == 1)
    n_neg = sum(1 for row in rows if row.label == 0)
    assert n_pos >= 400
    assert n_neg >= 400
    hold_pos = sum(1 for row in rows if row.split == "holdout" and row.label == 1)
    hold_neg = sum(1 for row in rows if row.split == "holdout" and row.label == 0)
    assert hold_pos / n_pos >= 0.20
    assert hold_neg / n_neg >= 0.20


def test_holdout_recall_and_hard_cases() -> None:
    rows = load_catalog()
    if not rows:
        pytest.skip("data/gate/labels.json ещё нет")
    hold = [row for row in rows if row.split == "holdout"]
    gate = load_content_gate("soft")
    tp = fn = 0
    hard_drop = 0
    for row in hold:
        gray = _read_gray(gate_root() / row.path)
        if gray is None:
            continue
        decision = gate.decide_crop(gray)
        if row.label == 1:
            if decision.accepted:
                tp += 1
            else:
                fn += 1
                if row.hard_case:
                    hard_drop += 1
    recall = tp / max(tp + fn, 1)
    assert recall >= 0.98, f"holdout recall={recall:.3f} tp={tp} fn={fn}"
    assert hard_drop == 0, f"soft gate dropped {hard_drop} hard_case positives"


def test_cli_gate_flag_optional() -> None:
    with pytest.raises(SystemExit) as exc:
        demo_main(["--help"])
    assert exc.value.code == 0
    spec = inspect.signature(run_scoresheet_pipeline)
    assert spec.parameters["gate_mode"].default == "soft"


def test_seg_flags_are_non_destructive() -> None:
    class _Box:
        def __init__(self) -> None:
            self.x1, self.y1, self.x2, self.y2 = 0, 0, 10, 10
            self.width, self.height = 10, 10

    class _Glyph:
        def __init__(self) -> None:
            self.box = _Box()
            self.mnist = np.full((28, 28), 255, dtype=np.uint8)

    glyphs = [_Glyph(), _Glyph()]
    flags = inspect_cell_glyphs(glyphs)
    assert len(flags) == 2
    assert glyphs[0].box.x1 == 0 and glyphs[0].box.x2 == 10


def test_gate_off_matches_p1_cell_reads() -> None:
    from chess_core.app.experiments.ocr import resolve_input
    from chess_core.app.experiments.ocr_glyphs import weights_dir
    from chess_core.app.experiments.ocr_stage12 import ocr_project_root, opencv_available

    baseline_path = project_root() / "output" / "ocr_runs" / "BASELINE_P1.json"
    if not baseline_path.is_file():
        pytest.skip("нет BASELINE_P1.json")
    if ocr_project_root() is None or not opencv_available():
        pytest.skip("нет stage12/opencv")
    if not (weights_dir() / "glyph_cnn.pt").is_file():
        pytest.skip("нет весов CNN")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline["sheets"]["image_0006"]["cell_reads"]
    dest = project_root() / "output" / "ocr_runs" / "image_0006_cnn_off"
    run = run_scoresheet_pipeline(
        resolve_input("image_0006.jpg"),
        dest,
        weights=weights_dir(),
        gate_mode="off",
    )
    assert list(run.cell_reads) == list(expected)
    assert all(text != "" for text in run.cell_reads)


def test_p1_regression_share_and_seg() -> None:
    root = project_root() / "output" / "ocr_runs"
    baseline_path = root / "BASELINE_P1.json"
    if not baseline_path.is_file():
        pytest.skip("нет BASELINE_P1.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    for sheet in ("image_0006", "image_0552"):
        report_path = root / f"{sheet}_cnn" / "report.json"
        if not report_path.is_file():
            pytest.skip(f"нет {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report.get("gate_mode", "soft") in {"off", "soft", "hard"}
        assert report["metrics"]["coverage"] == 1.0
        assert all(text != "" for text in report["cell_reads"])
        assert all(text != "" for text in report["legal_reads"])
        share = float(report["max_class_share"]["share"])
        before = float(baseline["sheets"][sheet]["max_class_share"]["share"])
        assert share <= before + 1e-9, f"{sheet} max_class_share {share} > {before}"
        seg = report["metrics"]["seg_err_rate"]
        if seg is not None:
            assert float(seg) <= float(baseline["sheets"][sheet]["seg_err_rate"]) + 1e-9
