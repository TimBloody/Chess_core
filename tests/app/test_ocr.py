"""Scoresheet OCR experiment: real stage12 grid, no invented SAN."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.experiments.ocr import (
    OcrStage,
    _STAGE_SPECS,
    _collect_stages,
    default_demo_input,
    pick_random_input,
    resolve_input,
    run_scoresheet_pipeline,
    write_samples,
)
from chess_core.app.experiments.ocr_glyphs import weights_dir
from chess_core.app.experiments.ocr_stage12 import (
    Stage12Run,
    ocr_project_root,
    opencv_available,
    raw_scoresheet_images,
)
from chess_core.tools.ocr_scoresheet import main as ocr_main

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _require_stage12() -> Path:
    root = ocr_project_root()
    if root is None:
        pytest.skip("соседний chess_scoresheet_ocr не найден")
    if not opencv_available():
        pytest.skip("opencv-python / numpy не установлены")
    photos = raw_scoresheet_images(root)
    if not photos:
        pytest.skip("нет data/raw/image_*.jpg")
    return root


def test_collect_stages_still_lists_missing_steps(tmp_path: Path) -> None:
    stage12 = Stage12Run(
        source=tmp_path / "blank.jpg",
        output_dir=tmp_path,
        angle_deg=0.0,
        grid_rows=21,
        grid_cols=9,
        order_count=0,
        occupied_cells=0,
        h_lines=0,
        v_lines=0,
        stage_files=(),
        cells_dir=tmp_path / "cells",
        cell_paths=(),
        notes=(),
    )
    cnn = OcrStage(
        "10_cnn_glyphs.png",
        "11. CNN",
        tmp_path / "10_cnn_glyphs.png",
        "нет весов",
    )
    stages = _collect_stages(stage12, cnn)
    assert [stage.key for stage in stages] == list(_STAGE_SPECS)
    assert stages[-1] is cnn
    assert all(
        "не дал картинку" in stage.note for stage in stages[:-1]
    )


def test_write_samples_creates_labelled_blanks(tmp_path: Path) -> None:
    _app()
    written = write_samples(tmp_path)
    names = {path.name for path in written}
    assert names == {"italian.png", "scholar.png", "rotated.png"}
    assert (tmp_path / "italian.json").is_file()
    assert (tmp_path / "manifest.json").is_file()


def test_resolve_input_defaults_to_raw_photo() -> None:
    _require_stage12()
    chosen = resolve_input(None)
    assert chosen.parent.name == "raw"
    assert chosen.suffix.lower() in {".jpg", ".jpeg"}


def test_resolve_input_finds_raw_by_name() -> None:
    _require_stage12()
    chosen = resolve_input("image_0006.jpg")
    assert chosen.name == "image_0006.jpg"
    assert chosen.is_file()


def test_default_demo_input_is_neighbour_scan() -> None:
    _require_stage12()
    chosen = default_demo_input()
    assert chosen.is_file()
    assert chosen.parent.name == "raw"


def test_pipeline_uses_stage12_grid_and_mnist_glyphs(tmp_path: Path) -> None:
    _require_stage12()
    source = resolve_input("image_0006.jpg")
    weights = weights_dir() if (weights_dir() / "glyph_cnn.pt").is_file() else None
    run = run_scoresheet_pipeline(source, tmp_path / "image_0006", weights=weights)
    keys = [stage.key for stage in run.stages]
    assert "05_grid_lines.jpg" in keys
    assert "04_game_table.jpg" in keys
    assert "08_cells_montage.jpg" not in keys
    assert "08_mser_glyphs.jpg" in keys
    assert "09_mnist_glyphs.jpg" in keys
    assert "01_deskewed.jpg" in keys
    assert "02_split_overlay.jpg" in keys
    assert "03_header.jpg" in keys
    assert "07_grid_preview.png" in keys
    assert "10_cnn_glyphs.png" in keys
    assert keys[-1] == "10_cnn_glyphs.png"
    for stage in run.stages:
        if stage.key == "10_cnn_glyphs.png" and not stage.path.is_file():
            continue
        assert stage.path.is_file(), stage.key
    assert (tmp_path / "image_0006" / "05_grid_lines.jpg").is_file()
    assert (tmp_path / "image_0006" / "stage12_report.json").is_file()
    assert run.engine in {"mser", "mser+cnn"}
    if weights is not None:
        assert run.engine == "mser+cnn"
        assert run.cell_reads
        assert (tmp_path / "image_0006" / "10_cnn_glyphs.png").is_file()
        assert all("C" not in text for text in run.cell_reads)
    elif run.engine == "mser":
        assert run.pgn == ""
        assert run.cell_reads == ()
    else:
        assert run.cell_reads
    assert run.grid_rows == 21
    assert run.grid_cols == 9
    assert run.h_lines == 22
    assert run.v_lines == 10
    assert (tmp_path / "image_0006" / "glyphs.json").is_file()
    assert not (tmp_path / "image_0006" / "game.pgn").exists()


def test_cli_on_real_blank(tmp_path: Path, capsys) -> None:
    _require_stage12()
    output = tmp_path / "run"
    assert ocr_main(["--input", "image_0006.jpg", "--output-dir", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "05_grid_lines.jpg" in printed
    assert "glyphs=" in printed
    assert not (output / "game.pgn").exists()
    assert (output / "glyphs.json").is_file()


def test_sidecar_json_is_not_used_as_recognition(tmp_path: Path) -> None:
    _require_stage12()
    _app()
    write_samples(tmp_path)
    source = tmp_path / "scholar.png"
    with pytest.raises(ValueError, match="scoresheet-10"):
        run_scoresheet_pipeline(source, tmp_path / "scholar_out")


def test_pick_random_stays_inside_raw_catalog() -> None:
    _require_stage12()
    allowed = set(raw_scoresheet_images())
    for _ in range(8):
        assert pick_random_input() in allowed
