"""P0: grammar never blanks a cell; gold games are legal."""

from __future__ import annotations

from pathlib import Path

import pytest

from chess_core.app.experiments.ocr import resolve_input, run_scoresheet_pipeline
from chess_core.app.experiments.ocr_glyphs import weights_dir
from chess_core.app.experiments.ocr_language import constrain_cell_reads, constrain_cells
from chess_core.app.experiments.ocr_stage12 import ocr_project_root, opencv_available
from chess_core.ocr.gold import list_gold_ids, load_gold
from chess_core.ocr.hypothesis import MISSING_MOVE


def test_constrain_never_returns_empty() -> None:
    reads = constrain_cell_reads(("", " ", "####", "c4", "zzzz"))
    assert len(reads) == 5
    assert all(text for text in reads)
    assert reads[0] == MISSING_MOVE
    hyps = constrain_cells(("", "c4", "nope"))
    assert hyps[0].low_confidence
    assert hyps[1].legal
    assert hyps[2].constraint == "raw_fallback"
    assert hyps[2].text == "nope"


@pytest.mark.parametrize("sheet_id", ["image_0006", "image_0552"])
def test_gold_plies_play_from_start(sheet_id: str) -> None:
    gold = load_gold(sheet_id)
    assert gold is not None
    hyps = constrain_cells(gold.plies)
    assert len(hyps) == len(gold.plies)
    assert all(item.text for item in hyps)
    if gold.ambiguous:
        assert hyps[0].legal
        return
    assert all(item.legal for item in hyps)


def _require_stage12() -> None:
    if ocr_project_root() is None:
        pytest.skip("соседний chess_scoresheet_ocr не найден")
    if not opencv_available():
        pytest.skip("opencv-python / numpy не установлены")
    if not (weights_dir() / "glyph_cnn.pt").is_file():
        pytest.skip("нет весов CNN")


@pytest.mark.parametrize("sheet_id", list(list_gold_ids()) or ["image_0006", "image_0552"])
def test_pipeline_coverage_is_complete(sheet_id: str, tmp_path: Path) -> None:
    _require_stage12()
    source = resolve_input(f"{sheet_id}.jpg")
    run = run_scoresheet_pipeline(
        source,
        tmp_path / sheet_id,
        weights=weights_dir(),
    )
    report = tmp_path / sheet_id / "report.json"
    assert report.is_file()
    assert run.cell_reads
    from chess_core.app.experiments.ocr_language import constrain_cells as _cells

    hyps = _cells(run.cell_reads)
    assert len(hyps) == len(run.cell_reads)
    assert all(item.text for item in hyps)
    dump_legal = (tmp_path / sheet_id / "glyphs.json").read_text(encoding="utf-8")
    assert '"legal_reads"' in dump_legal
    import json

    payload = json.loads((tmp_path / sheet_id / "report.json").read_text(encoding="utf-8"))
    assert payload["metrics"]["coverage"] == 1.0
    assert payload["metrics"].get("empty_legal", 0) == 0
    assert all(text for text in payload["legal_reads"])
    assert "role_confusion" in payload
    assert "max_class_share" in payload
