"""P5.0c: blind sheets carry no labels, and the shuffle is not the grid order."""

from __future__ import annotations

import json

import numpy as np

from chess_core.infra.paths import project_root
from chess_core.ocr.blind_sheet import render_blind_sheet, shuffled_indices, spearman
from chess_core.ocr.gold import gold_dir
from chess_core.tools.audit_p5_diag_c import SEED_PAD, SEED_RAW, SEED_X4, anonymous_id


def test_blind_sheet_rejects_labels() -> None:
    image = np.full((8, 8), 200, dtype=np.uint8)
    _canvas, captions = render_blind_sheet([image, image], ["g001", "g002"])
    assert captions == ["g001", "g002"]
    for leaked in ("f_c", "r01", "c02", "KN", "0.88"):
        try:
            render_blind_sheet([image], [leaked])
        except ValueError:
            continue
        raise AssertionError(f"caption accepted {leaked}")


def test_shuffle_is_uncorrelated_with_grid() -> None:
    rows = json.loads((gold_dir() / "glyphs_real.json").read_text(encoding="utf-8"))["glyphs"]
    grids = []
    for row in rows:
        stem = str(row["cell"]).replace(".png", "")
        grid_r = int(stem.split("_r")[1].split("_")[0])
        grid_c = int(stem.split("_c")[1])
        grids.append((grid_r, grid_c))
    for seed in (SEED_RAW, SEED_PAD, SEED_X4):
        order = shuffled_indices(len(rows), seed)
        assert order != list(range(len(rows)))
        assert abs(spearman(list(range(len(order))), [grids[i][0] for i in order])) < 0.35
        assert abs(spearman(list(range(len(order))), [grids[i][1] for i in order])) < 0.35
        assert shuffled_indices(len(rows), seed) == order


def test_levels_name_the_same_ids() -> None:
    ids = [anonymous_id(i) for i in range(59)]
    assert ids[0] == "g001" and ids[-1] == "g059"
    assert len(set(ids)) == 59


def test_blind_labels_cover_every_level() -> None:
    payload = json.loads((gold_dir() / "glyphs_real_blind.json").read_text(encoding="utf-8"))
    ids = [anonymous_id(i) for i in range(59)]
    assert [row["id"] for row in payload["glyphs"]] == ids
    for name in ("raw", "pad28", "pad28x4"):
        rows = payload["levels"][name]
        assert [row["id"] for row in rows] == ids
        for row in rows:
            assert row.get("role") or row.get("readable") is False


def test_saved_report_matches_seed_and_coverage() -> None:
    root = project_root() / "output" / "ocr_runs"
    for sheet in ("image_0006", "image_0552"):
        report = json.loads((root / f"{sheet}_cnn" / "report.json").read_text(encoding="utf-8"))
        assert report["metrics"]["coverage"] == 1.0
    ladder = json.loads((root / "p5_diag" / "report.json").read_text(encoding="utf-8"))
    assert ladder["ladder"]["B0"]["top1"]["n"] == 2000
    assert abs(float(ladder["ladder"]["B0"]["top1"]["p"]) - 0.968) < 1e-9
