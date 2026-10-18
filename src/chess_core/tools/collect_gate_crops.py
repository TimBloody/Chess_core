"""Cut real gate positives/negatives from scoresheets. Split is by sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from chess_core.app.experiments.ocr import default_output_dir, resolve_input
from chess_core.app.experiments.ocr_mser import mnist_pad, segment_cell, to_gray
from chess_core.app.experiments.ocr_stage12 import raw_scoresheet_images, run_stage12_preprocess
from chess_core.infra.paths import project_root
from chess_core.ocr.gate.catalog import (
    CropRecord,
    file_hash,
    gate_root,
    save_catalog,
    split_path,
)
from chess_core.ocr.gate.features import extract_raw_features, is_hard_positive
from chess_core.ocr.gate.geometry import SheetGeometry

EVAL_SHEETS = frozenset({"image_0006", "image_0552"})
TRAIN_SHEETS = ("image_0551", "image_0001", "image_0007")
HOLDOUT_SHEETS = ("image_0008", "image_0009")


def _write_png(path: Path, gray: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", gray)[1].tofile(str(path))


def _read_gray(path: Path) -> np.ndarray | None:
    import cv2

    if not path.is_file():
        return None
    encoded = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)


def _read_bgr(path: Path) -> np.ndarray | None:
    import cv2

    if not path.is_file():
        return None
    encoded = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)


def _run_dir_for(stem: str) -> Path:
    cnn = default_output_dir(stem + "_cnn")
    if (cnn / "04_game_table.jpg").is_file() or (cnn / "cells").is_dir():
        return cnn
    return default_output_dir(stem + "_gate")


def _ensure_stage12(stem: str) -> Path:
    dest = _run_dir_for(stem)
    if (dest / "stage12_report.json").is_file() and (dest / "04_game_table.jpg").is_file():
        return dest
    source = resolve_input(f"{stem}.jpg")
    dest.mkdir(parents=True, exist_ok=True)
    print(f"stage12 {stem} -> {dest}", flush=True)
    run_stage12_preprocess(source, dest)
    return dest


def _load_geometry(dest: Path) -> SheetGeometry:
    report = json.loads((dest / "stage12_report.json").read_text(encoding="utf-8"))
    return SheetGeometry.from_meta(report.get("meta") or {}, report=report)


def _iter_line_cells(h_lines: tuple[int, ...], v_lines: tuple[int, ...]) -> list[tuple[int, int, int, int, int, int]]:
    cells = []
    for r in range(len(h_lines) - 1):
        for c in range(len(v_lines) - 1):
            y1, y2 = h_lines[r], h_lines[r + 1]
            x1, x2 = v_lines[c], v_lines[c + 1]
            if y2 - y1 < 8 or x2 - x1 < 8:
                continue
            cells.append((r, c, x1, y1, x2, y2))
    return cells


def _edge_strips(gray: np.ndarray) -> list[np.ndarray]:
    h, w = gray.shape
    t = max(4, min(8, h // 10, w // 10))
    strips = [
        gray[:t, :],
        gray[-t:, :],
        gray[:, :t],
        gray[:, -t:],
        gray[: t + 2, : t + 2],
        gray[: t + 2, -t - 2 :],
        gray[-t - 2 :, : t + 2],
        gray[-t - 2 :, -t - 2 :],
    ]
    return [item for item in strips if item.size and item.shape[0] >= 4 and item.shape[1] >= 4]


def _line_bands(
    gray: np.ndarray,
    h_lines: tuple[int, ...],
    v_lines: tuple[int, ...],
    *,
    band: int = 6,
    tile: int = 48,
) -> list[tuple[np.ndarray, str, list[int]]]:
    h, w = gray.shape[:2]
    out: list[tuple[np.ndarray, str, list[int]]] = []
    for y in h_lines:
        y1, y2 = max(0, y - band), min(h, y + band)
        for x in range(0, max(w - tile, 1), tile * 2):
            crop = gray[y1:y2, x : x + tile]
            if crop.size and crop.shape[0] >= 3 and crop.shape[1] >= 8:
                out.append((crop, "h-grid", [x, y1, x + tile, y2]))
        for x in v_lines:
            x1, x2 = max(0, x - band * 2), min(w, x + band * 2)
            cross = gray[y1:y2, x1:x2]
            if cross.size and min(cross.shape[:2]) >= 3:
                out.append((cross, "grid-cross", [x1, y1, x2, y2]))
    for x in v_lines:
        x1, x2 = max(0, x - band), min(w, x + band)
        for y in range(0, max(h - tile, 1), tile * 2):
            crop = gray[y : y + tile, x1:x2]
            if crop.size and crop.shape[1] >= 3 and crop.shape[0] >= 8:
                out.append((crop, "v-grid", [x1, y, x2, y + tile]))
    mw = max(12, w // 40)
    for y in range(0, max(h - tile, 1), tile * 3):
        crop = gray[y : y + tile, :mw]
        if crop.size:
            out.append((crop, "page-margin", [0, y, mw, y + tile]))
    return out


def _header_tiles(header: np.ndarray, *, stride: int = 40, size: int = 48) -> list[np.ndarray]:
    h, w = header.shape[:2]
    tiles = []
    for y in range(0, max(h - size, 1), stride):
        for x in range(0, max(w - size, 1), stride):
            tile = header[y : y + size, x : x + size]
            if tile.size == 0:
                continue
            feats = extract_raw_features(tile)
            if 0.02 < feats.ink_ratio < 0.55:
                tiles.append(tile)
    return tiles


def _save_record(
    *,
    rows: list[CropRecord],
    gray: np.ndarray,
    label: int,
    sheet: str,
    cell: str,
    bbox: list[int],
    split: str,
    notes: str,
    hard: bool,
    index: int,
) -> None:
    kind = "positives" if label == 1 else "negatives"
    base = "holdout" if split == "holdout" else ""
    rel_dir = Path(base) / kind if base else Path(kind)
    name = f"{sheet}_{cell}_{index:04d}.png"
    raw_rel = rel_dir / "raw" / name
    norm_rel = rel_dir / "norm" / name
    raw_abs = gate_root() / raw_rel
    norm_abs = gate_root() / norm_rel
    _write_png(raw_abs, gray)
    _write_png(norm_abs, mnist_pad(gray))
    rows.append(
        CropRecord(
            path=raw_rel.as_posix(),
            norm_path=norm_rel.as_posix(),
            label=label,
            source_sheet=sheet,
            cell=cell,
            bbox=bbox,
            hard_case=hard,
            split=split,
            notes=notes,
            sha256=file_hash(raw_abs),
        )
    )


def harvest_sheet(stem: str, split: str, *, max_pos: int, max_neg: int) -> list[CropRecord]:
    dest = _ensure_stage12(stem)
    geometry = _load_geometry(dest)
    game = _read_gray(dest / "04_game_table.jpg")
    header = _read_gray(dest / "03_header.jpg")
    rows: list[CropRecord] = []
    n_pos = n_neg = 0
    cells_dir = dest / "cells"
    occupied = sorted(cells_dir.glob("*.png")) if cells_dir.is_dir() else []
    for path in occupied:
        if n_pos >= max_pos:
            break
        gray = _read_gray(path)
        if gray is None:
            continue
        split_cell = segment_cell(gray)
        parsed = path.stem
        for idx, glyph in enumerate(split_cell.glyphs):
            if n_pos >= max_pos:
                break
            crop = gray[glyph.box.y1 : glyph.box.y2, glyph.box.x1 : glyph.box.x2]
            if crop.size == 0:
                continue
            feats = extract_raw_features(crop)
            _save_record(
                rows=rows,
                gray=crop,
                label=1,
                sheet=stem,
                cell=parsed,
                bbox=[glyph.box.x1, glyph.box.y1, glyph.box.x2, glyph.box.y2],
                split=split,
                notes="occupied-glyph",
                hard=is_hard_positive(feats),
                index=n_pos,
            )
            n_pos += 1
        if split_cell.content is None:
            continue
        for strip in _edge_strips(gray):
            if n_neg >= max_neg:
                break
            feats = extract_raw_features(strip)
            if feats.ink_ratio < 0.01:
                continue
            _save_record(
                rows=rows,
                gray=strip,
                label=0,
                sheet=stem,
                cell=parsed,
                bbox=[0, 0, strip.shape[1], strip.shape[0]],
                split=split,
                notes="cell-border",
                hard=False,
                index=n_neg,
            )
            n_neg += 1
    if header is not None:
        for tile in _header_tiles(header)[:80]:
            if n_neg >= max_neg:
                break
            _save_record(
                rows=rows,
                gray=tile,
                label=0,
                sheet=stem,
                cell="header",
                bbox=[0, 0, tile.shape[1], tile.shape[0]],
                split=split,
                notes="header-print",
                hard=False,
                index=n_neg,
            )
            n_neg += 1
    if game is not None and geometry.h_lines and geometry.v_lines:
        for r, c, x1, y1, x2, y2 in _iter_line_cells(geometry.h_lines, geometry.v_lines):
            if n_neg >= max_neg:
                break
            zone = None
            if c in geometry.skipped_columns:
                zone = "printed_index"
            elif r in geometry.skipped_rows or r < geometry.first_data_row:
                zone = "printed_header"
            crop = game[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            feats = extract_raw_features(crop)
            if zone is None and feats.ink_ratio > 0.04:
                continue
            if feats.ink_ratio < 0.008 and zone is None:
                notes = "empty-cell"
            else:
                notes = zone or "grid-line"
            _save_record(
                rows=rows,
                gray=crop,
                label=0,
                sheet=stem,
                cell=f"r{r:02d}_c{c:02d}",
                bbox=[x1, y1, x2, y2],
                split=split,
                notes=notes,
                hard=False,
                index=n_neg,
            )
            n_neg += 1
        for crop, notes, bbox in _line_bands(game, geometry.h_lines, geometry.v_lines):
            if n_neg >= max_neg:
                break
            feats = extract_raw_features(crop)
            if feats.ink_ratio < 0.004:
                continue
            _save_record(
                rows=rows,
                gray=crop,
                label=0,
                sheet=stem,
                cell="grid",
                bbox=bbox,
                split=split,
                notes=notes,
                hard=False,
                index=n_neg,
            )
            n_neg += 1
    print(f"{stem} split={split} pos={n_pos} neg={n_neg}", flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Собрать raw/norm кропы для content-gate.")
    parser.add_argument("--max-pos-per-sheet", type=int, default=220)
    parser.add_argument("--max-neg-per-sheet", type=int, default=220)
    args = parser.parse_args(argv)
    available = {path.stem for path in raw_scoresheet_images()}
    extra = sorted(stem for stem in available if stem not in EVAL_SHEETS)
    train_stems = [stem for stem in TRAIN_SHEETS if stem in available]
    hold_stems = [stem for stem in HOLDOUT_SHEETS if stem in available]
    leftover = [stem for stem in extra if stem not in train_stems and stem not in hold_stems]
    if len(train_stems) < 2:
        train_stems.extend(leftover[: max(0, 3 - len(train_stems))])
        leftover = [stem for stem in leftover if stem not in train_stems]
    if not hold_stems:
        hold_stems = leftover[:1]
        leftover = leftover[1:]
    if leftover and len(hold_stems) == 1 and len(train_stems) >= 3:
        # ~30% of sheets: keep one extra holdout if we have 5+ usable sheets
        pass
    print(f"gate train sheets={train_stems} holdout={hold_stems}", flush=True)
    rows: list[CropRecord] = []
    for stem in train_stems:
        if stem in EVAL_SHEETS:
            raise RuntimeError(f"{stem} is an eval sheet and must not enter the gate corpus")
        if stem not in available:
            print(f"skip missing {stem}")
            continue
        rows.extend(
            harvest_sheet(
                stem,
                "train",
                max_pos=args.max_pos_per_sheet,
                max_neg=args.max_neg_per_sheet,
            )
        )
    for stem in hold_stems:
        if stem in EVAL_SHEETS:
            raise RuntimeError(f"{stem} is an eval sheet and must not enter the gate corpus")
        if stem not in available:
            print(f"skip missing {stem}")
            continue
        rows.extend(
            harvest_sheet(
                stem,
                "holdout",
                max_pos=args.max_pos_per_sheet,
                max_neg=args.max_neg_per_sheet,
            )
        )
    n_pos = sum(1 for row in rows if row.label == 1)
    n_neg = sum(1 for row in rows if row.label == 0)
    if n_pos < 400 or n_neg < 400:
        raise SystemExit(f"мало кропов: positives={n_pos} negatives={n_neg}, нужно >=400")
    save_catalog(rows)
    split_payload = {
        "train_sheets": sorted({row.source_sheet for row in rows if row.split == "train"}),
        "holdout_sheets": sorted({row.source_sheet for row in rows if row.split == "holdout"}),
        "eval_sheets": sorted(EVAL_SHEETS),
        "n_train": sum(1 for row in rows if row.split == "train"),
        "n_holdout": sum(1 for row in rows if row.split == "holdout"),
        "n_pos": n_pos,
        "n_neg": n_neg,
        "seed": 0,
        "method": "split-by-sheet",
        "note": "0006/0552 не входят в корпус гейта: они золотые eval-листы.",
    }
    split_path().write_text(json.dumps(split_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(split_payload, ensure_ascii=False, indent=2))
    print(f"labels={gate_root() / 'labels.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
