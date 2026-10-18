"""Lazy adapter to the neighbour scoresheet OCR stage12 (deskew / split / grid)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from chess_core.infra.paths import project_root

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def ocr_project_root() -> Path | None:
    env = Path(__import__("os").environ.get("CHESS_SCORESHEET_OCR", ""))
    candidates = [
        env,
        project_root().parent / "DZ_VUZ" / "AI" / "chess_scoresheet_ocr",
        Path.home() / "OneDrive" / "Документы" / "DZ_VUZ" / "AI" / "chess_scoresheet_ocr",
    ]
    for candidate in candidates:
        if candidate and (candidate / "src" / "stage12" / "pipeline.py").is_file():
            return candidate.resolve()
    return None


def raw_scoresheet_images(root: Path | None = None) -> list[Path]:
    base = (root or ocr_project_root() or Path()) / "data" / "raw"
    if not base.is_dir():
        return []
    return sorted(
        path
        for path in base.iterdir()
        if path.is_file()
        and path.suffix.lower() in _IMAGE_SUFFIXES
        and path.name.lower().startswith("image_")
    )


def _inject_ocr_path(root: Path) -> None:
    src = root / "src"
    # Same directories as scripts/run_modern_ocr.py. stage12 must win so
    # `from pipeline import preprocess_sheet` is stage12.pipeline, not src/pipeline.
    for directory in ("pipeline", "ocr", "validation", "stage12"):
        path = str(src / directory)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


def _patch_opencv_hough_shape() -> None:
    """stage12 unpacks `lines[:, 0]`; OpenCV 5 returns (N, 4) instead of (N, 1, 4)."""

    import cv2

    original = cv2.HoughLinesP
    if getattr(original, "_chess_core_hough_patch", False):
        return

    def hough_lines_p(*args, **kwargs):
        lines = original(*args, **kwargs)
        if lines is None:
            return None
        if getattr(lines, "ndim", 0) == 2 and lines.shape[-1] == 4:
            return lines.reshape(-1, 1, 4)
        return lines

    hough_lines_p._chess_core_hough_patch = True  # type: ignore[attr-defined]
    cv2.HoughLinesP = hough_lines_p


@dataclass(frozen=True, slots=True)
class Stage12Run:
    source: Path
    output_dir: Path
    angle_deg: float
    grid_rows: int
    grid_cols: int
    order_count: int
    occupied_cells: int
    h_lines: int
    v_lines: int
    stage_files: tuple[Path, ...]
    cells_dir: Path
    cell_paths: tuple[Path, ...]
    notes: tuple[str, ...]


def _ink_score(cell_bgr: Any) -> float:
    from chess_core.app.experiments.ocr_mser import ink_mass

    return float(ink_mass(cell_bgr))


def run_stage12_preprocess(
    image_path: Path,
    output_dir: Path,
    *,
    max_preview_cells: int = 12,
    ink_threshold: float = 70.0,
    empty_patience: int = 3,
) -> Stage12Run:
    """Deskew, split header/table, detect the real move grid, crop cells."""

    root = ocr_project_root()
    if root is None:
        raise FileNotFoundError("chess_scoresheet_ocr project not found")
    if not opencv_available():
        raise RuntimeError("нужны opencv-python и numpy, чтобы вызвать stage12 соседнего OCR")

    _patch_opencv_hough_shape()
    _inject_ocr_path(root)
    from grid import draw_grid_overlays  # noqa: E402
    from pipeline import preprocess_sheet  # noqa: E402  # stage12.pipeline
    from scoresheet_layout import draw_preview  # noqa: E402
    from sheet_io import imwrite_bgr, read_bgr  # noqa: E402
    from split import draw_split_overlay  # noqa: E402

    source = image_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    original = read_bgr(source)
    prep = preprocess_sheet(
        original,
        deskew_method="projection",
        do_split=True,
        do_grid=True,
        grid_padding=0,
        order_mode="scoresheet-10",
        input_label=str(source),
    )
    saved: list[Path] = []

    def dump(name: str, image: Any) -> Path:
        path = output_dir / name
        imwrite_bgr(path, image)
        saved.append(path)
        return path

    dump("00_original.jpg", original)
    dump("01_deskewed.jpg", prep.deskew.deskewed)
    notes = [
        f"stage12 из {root}",
        f"deskew {prep.deskew.angle_deg:.2f} deg",
    ]
    if prep.split is not None:
        dump("02_split_overlay.jpg", draw_split_overlay(prep.deskew.deskewed, prep.split.columns, prep.split.boundary_y))
        dump("03_header.jpg", prep.split.header)
        dump("04_game_table.jpg", prep.split.game)
        notes.append(f"split boundary_y={prep.split.boundary_y}")
    if prep.grid is None:
        raise RuntimeError("stage12 не нашёл сетку таблицы ходов")

    game = prep.split.game if prep.split is not None else prep.deskew.deskewed
    overlays = draw_grid_overlays(game, prep.grid.grid)
    dump("05_grid_lines.jpg", overlays["lines"])
    dump("06_grid_order.jpg", overlays["order"])
    dump("07_grid_preview.png", draw_preview(game, prep.grid.cells))

    cells_dir = output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)
    occupied = 0
    preview_crops: list[Any] = []
    cell_paths: list[Path] = []
    empty_run = 0

    from chess_core.app.experiments.ocr_mser import glyph_montage, mnist_montage, segment_cell

    for order_index, (row, col) in enumerate(prep.grid.order):
        x1, y1, x2, y2 = prep.grid.cells[row][col]
        crop = game[y1 : y2 + 1, x1 : x2 + 1].copy()
        ink = _ink_score(crop)
        if ink >= ink_threshold:
            occupied += 1
            empty_run = 0
            cell_path = cells_dir / f"{order_index:04d}_r{row:02d}_c{col:02d}.png"
            imwrite_bgr(cell_path, crop)
            cell_paths.append(cell_path)
            if len(preview_crops) < max_preview_cells:
                preview_crops.append(crop)
        else:
            empty_run += 1
            if occupied >= 2 and empty_run >= empty_patience:
                break
    montage = glyph_montage(preview_crops, max_cells=max_preview_cells)
    if montage is not None:
        dump("08_mser_glyphs.jpg", montage)
    mnist = mnist_montage(preview_crops, max_cells=max_preview_cells)
    if mnist is not None:
        dump("09_mnist_glyphs.jpg", mnist)
    import cv2

    mnist_dir = cells_dir / "mnist"
    for crop, cell_path in zip(preview_crops, cell_paths[: len(preview_crops)]):
        split = segment_cell(crop)
        if not split.glyphs:
            continue
        cell_mnist = mnist_dir / cell_path.stem
        cell_mnist.mkdir(parents=True, exist_ok=True)
        for index, glyph in enumerate(split.glyphs):
            imwrite_bgr(
                cell_mnist / f"{index:02d}.png",
                cv2.cvtColor(glyph.mnist, cv2.COLOR_GRAY2BGR),
            )

    report = {
        "source": str(source),
        "angle_deg": prep.deskew.angle_deg,
        "grid_rows": prep.grid.grid.grid_rows,
        "grid_cols": prep.grid.grid.grid_cols,
        "order_count": len(prep.grid.order),
        "occupied_cells": occupied,
        "h_lines": len(prep.grid.h_lines),
        "v_lines": len(prep.grid.v_lines),
        "meta": prep.grid.meta,
    }
    (output_dir / "stage12_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    notes.append(
        f"сетка {report['grid_rows']}x{report['grid_cols']}, "
        f"линий H={report['h_lines']} V={report['v_lines']}, "
        f"занятых клеток {occupied}/{len(prep.grid.order)}"
    )
    return Stage12Run(
        source=source,
        output_dir=output_dir,
        angle_deg=float(prep.deskew.angle_deg),
        grid_rows=int(report["grid_rows"]),
        grid_cols=int(report["grid_cols"]),
        order_count=len(prep.grid.order),
        occupied_cells=occupied,
        h_lines=int(report["h_lines"]),
        v_lines=int(report["v_lines"]),
        stage_files=tuple(saved),
        cells_dir=cells_dir,
        cell_paths=tuple(cell_paths),
        notes=tuple(notes),
    )
