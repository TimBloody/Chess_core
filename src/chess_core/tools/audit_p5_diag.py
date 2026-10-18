"""P5.0b: is the 0.14 glyph score a bad alignment (H1) or a low-level input gap (H2)?

No training. Real crops are never used as labels for a fit.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from chess_core.app.experiments.ocr_glyphs import (
    emnist_keep_indices,
    emnist_root,
    load_glyph_recognizer,
    to_mnist_glyph,
    weights_dir,
)
from chess_core.app.experiments.ocr_mser import segment_cell, to_gray
from chess_core.infra.paths import project_root
from chess_core.ocr.diag_stats import FEATURE_NAMES, crop_features, proportion, quantiles
from chess_core.ocr.glyph_prep import PrepConfig, prepare_crop
from chess_core.ocr.gold import gold_dir
from chess_core.ocr.roles import ROLE_IDS

SEED = 0
N_EMNIST = 2000
NIST_SOURCE = 128


def _write_png(path: Path, image: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", image)[1].tofile(str(path))


def _diag_dir() -> Path:
    path = project_root() / "output" / "ocr_runs" / "p5_diag"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_real() -> list[dict[str, object]]:
    payload = json.loads((gold_dir() / "glyphs_real.json").read_text(encoding="utf-8"))
    return list(payload["glyphs"])


def _predict(tiles: list[np.ndarray], model, charset: tuple[str, ...], device) -> list[tuple[str, float, tuple[str, ...]]]:
    import torch

    if not tiles:
        return []
    out: list[tuple[str, float, tuple[str, ...]]] = []
    chunk = 256
    for start in range(0, len(tiles), chunk):
        batch = np.stack(tiles[start : start + chunk], axis=0).astype(np.float32) / 255.0
        tensor = torch.from_numpy(np.ascontiguousarray(batch)).unsqueeze(1).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(tensor), dim=1)
            top = torch.topk(probs, k=min(5, len(charset)), dim=1)
        for row in range(batch.shape[0]):
            names = tuple(charset[int(i)] for i in top.indices[row].tolist())
            out.append((names[0], float(top.values[row, 0]), names))
    return out


def _hits(golds: list[str], preds: list[tuple[str, float, tuple[str, ...]]], k: int) -> int:
    return sum(gold in ranked[:k] if k > 1 else int(ranked[0] == gold) for gold, (_p, _c, ranked) in zip(golds, preds))


def _acc_block(golds: list[str], preds: list[tuple[str, float, tuple[str, ...]]]) -> dict[str, object]:
    n = len(golds)
    top1 = _hits(golds, preds, 1)
    top5 = sum(gold in item[2][:5] for gold, item in zip(golds, preds))
    return {"top1": proportion(top1, n), "top5": proportion(top5, n)}


def _sheet_component_widths(sheet_id: str) -> list[float]:
    cells = sorted((project_root() / "output" / "ocr_runs" / f"{sheet_id}_cnn" / "cells").glob("*.png"))
    widths: list[float] = []
    for cell in cells:
        split = segment_cell(cell)
        widths.extend(float(glyph.box.width) for glyph in split.glyphs)
    return widths


def geometry_report(rows: list[dict[str, object]]) -> dict[str, object]:
    by_sheet: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_sheet.setdefault(str(row["sheet_id"]), []).append(row)
    cells_out = []
    infected = 0
    wide_n = narrow_n = 0
    n_cells = 0
    for sheet_id, group in by_sheet.items():
        population = _sheet_component_widths(sheet_id)
        median = float(np.median(population)) if population else 1.0
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in group:
            grouped.setdefault(str(row["cell"]), []).append(row)
        for cell, glyphs in grouped.items():
            n_cells += 1
            flags = []
            for glyph in glyphs:
                box = glyph["bbox"]
                width = float(box[2] - box[0])
                kind = "ok"
                if width > 1.6 * median:
                    kind = "wide"
                    wide_n += 1
                elif width < 0.5 * median:
                    kind = "narrow"
                    narrow_n += 1
                flags.append({"glyph_index": glyph["glyph_index"], "width": width, "flag": kind})
            bad = any(item["flag"] != "ok" for item in flags)
            infected += int(bad)
            cells_out.append(
                {
                    "sheet_id": sheet_id,
                    "cell": cell,
                    "ply": glyphs[0]["ply"],
                    "median_sheet_width": median,
                    "infected": bad,
                    "components": flags,
                }
            )
    return {
        "n_count_matched_cells": n_cells,
        "infected_cells": infected,
        "infected_share": proportion(infected, n_cells),
        "wide_components": wide_n,
        "narrow_components": narrow_n,
        "rule": "wide > 1.6x sheet median width; narrow < 0.5x. Median is all MSER glyphs on the sheet.",
        "cells": cells_out,
    }


def _contact_sheet(rows, crops, norms, preds, path: Path) -> None:
    import cv2

    thumb = 120
    label_h = 46
    pair_w = thumb * 2 + 16
    cols = 4
    rows_n = (len(rows) + cols - 1) // cols
    canvas = np.full((rows_n * (thumb + label_h + 8) + 8, cols * (pair_w + 8) + 8, 3), 245, dtype=np.uint8)
    for index, (row, crop, norm, pred) in enumerate(zip(rows, crops, norms, preds)):
        r, c = divmod(index, cols)
        x = 8 + c * (pair_w + 8)
        y = 8 + r * (thumb + label_h + 8)
        raw = _fit(crop, thumb)
        pad = _fit(norm, thumb)
        canvas[y : y + raw.shape[0], x : x + raw.shape[1]] = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
        canvas[y : y + pad.shape[0], x + thumb + 8 : x + thumb + 8 + pad.shape[1]] = cv2.cvtColor(
            pad, cv2.COLOR_GRAY2BGR
        )
        cell = str(row["cell"])
        rc = cell.split("_", 1)[-1].replace(".png", "")
        text1 = f"{index:02d} {row['sheet_id'][-4:]} {rc} gold={row['role']}"
        text2 = f"pred={pred[0]} {pred[1]:.2f}"
        cv2.putText(canvas, text1, (x, y + thumb + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (20, 20, 20), 1, cv2.LINE_AA)
        cv2.putText(canvas, text2, (x, y + thumb + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (20, 20, 20), 1, cv2.LINE_AA)
    _write_png(path, canvas)


def _fit(gray: np.ndarray, side: int) -> np.ndarray:
    import cv2

    h, w = gray.shape[:2]
    scale = side / max(h, w, 1)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    return cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_NEAREST)


def _hist_png(series: dict[str, list[float]], path: Path) -> None:
    import cv2

    names = list(series)
    canvas = np.full((40 + 150 * len(names), 640, 3), 255, dtype=np.uint8)
    for row, name in enumerate(names):
        values = np.asarray(series[name], dtype=np.float64)
        if values.size == 0:
            continue
        counts, _edges = np.histogram(values, bins=16)
        peak = max(int(counts.max()), 1)
        y0 = 40 + row * 150 + 110
        cv2.putText(canvas, name, (16, y0 - 116), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1)
        width = 560 // len(counts)
        for i, count in enumerate(counts.tolist()):
            h = int(90 * count / peak)
            x = 40 + i * width
            cv2.rectangle(canvas, (x, y0 - h), (x + width - 2, y0), (40, 80, 180), -1)
    _write_png(path, canvas)


def _load_emnist(n: int) -> tuple[list[np.ndarray], list[str], list[int]]:
    from torchvision.datasets import EMNIST

    dataset = EMNIST(root=str(emnist_root()), split="byclass", train=False, download=False)
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = dataset.targets.numpy() if hasattr(dataset.targets, "numpy") else np.asarray(dataset.targets)
    keep = emnist_keep_indices()
    idxs = np.asarray([i for i, target in enumerate(targets.tolist()) if int(target) in keep], dtype=np.int64)
    rng = np.random.default_rng(SEED)
    chosen = rng.choice(idxs, size=min(n, len(idxs)), replace=False)
    tiles = []
    labels = []
    for index in chosen.tolist():
        raw = np.asarray(data[index], dtype=np.uint8)
        tiles.append(to_mnist_glyph(raw, invert=True))
        labels.append(keep[int(targets[index])])
    return tiles, labels, chosen.tolist()


def _median_grad(tiles: list[np.ndarray]) -> float:
    import cv2

    values = []
    for tile in tiles:
        gx = cv2.Sobel(tile, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(tile, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.hypot(gx, gy)
        ink = tile < 200
        if np.any(ink):
            values.append(float(np.median(mag[ink])))
    return float(np.median(values)) if values else 0.0


def _match_blur(reference: list[np.ndarray], donors: list[np.ndarray]) -> float:
    import cv2

    target = _median_grad(reference)
    best_sigma = 0.0
    best_gap = abs(_median_grad(donors) - target)
    for sigma in np.linspace(0.4, 2.4, 11):
        blurred = [cv2.GaussianBlur(tile, (0, 0), float(sigma)) for tile in donors]
        gap = abs(_median_grad(blurred) - target)
        if gap < best_gap:
            best_gap = gap
            best_sigma = float(sigma)
    return best_sigma


def _match_stroke(tiles: list[np.ndarray], target: float) -> int:
    """Signed kernel radius. Positive dilates ink, negative erodes. 0 leaves it."""

    import cv2

    from chess_core.ocr.diag_stats import stroke_width_px

    def median_stroke(images: list[np.ndarray]) -> float:
        return float(np.median([stroke_width_px(image) for image in images]))

    current = median_stroke(tiles)
    if abs(current - target) < 0.25:
        return 0
    direction = 1 if target > current else -1
    best = 0
    best_gap = abs(current - target)
    for radius in range(1, 4):
        k = 2 * radius + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        changed = []
        for tile in tiles:
            ink = cv2.dilate(255 - tile, kernel) if direction > 0 else cv2.erode(255 - tile, kernel)
            changed.append(np.clip(255 - ink, 0, 255).astype(np.uint8))
        gap = abs(median_stroke(changed) - target)
        if gap < best_gap:
            best_gap = gap
            best = direction * radius
    return best


def _apply_stroke(tile: np.ndarray, radius: int) -> np.ndarray:
    import cv2

    if radius == 0:
        return tile
    k = 2 * abs(radius) + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ink = cv2.dilate(255 - tile, kernel) if radius > 0 else cv2.erode(255 - tile, kernel)
    return np.clip(255 - ink, 0, 255).astype(np.uint8)


def _apply_contrast(tile: np.ndarray, src_lo: float, src_hi: float, dst_lo: float, dst_hi: float) -> np.ndarray:
    gray = tile.astype(np.float32)
    ink = gray < 175
    span = max(src_hi - src_lo, 1.0)
    mapped = dst_lo + (gray - src_lo) * ((dst_hi - dst_lo) / span)
    out = gray.copy()
    out[ink] = np.clip(mapped[ink], 0, 255)
    return out.astype(np.uint8)


def _ink_range(tiles: list[np.ndarray]) -> tuple[float, float]:
    values = []
    for tile in tiles:
        ink = tile < 175
        if np.any(ink):
            values.append(tile[ink].astype(np.float64))
    if not values:
        return 0.0, 255.0
    joined = np.concatenate(values)
    return float(np.quantile(joined, 0.05)), float(np.quantile(joined, 0.95))


def _resize_square(tile: np.ndarray, side: int) -> np.ndarray:
    import cv2

    side = max(4, int(side))
    small = cv2.resize(tile, (side, side), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (28, 28), interpolation=cv2.INTER_CUBIC)


def _degrade(
    tiles: list[np.ndarray],
    *,
    side: int | None,
    sigma: float,
    stroke: int,
    contrast: tuple[float, float, float, float] | None,
    jitter: dict[str, float] | None,
    rng: np.random.Generator | None,
) -> list[np.ndarray]:
    import cv2

    out = []
    for tile in tiles:
        image = tile
        this_side = side
        this_sigma = sigma
        this_stroke = stroke
        this_contrast = contrast
        if jitter is not None and rng is not None:
            this_side = int(rng.integers(int(jitter["side_lo"]), int(jitter["side_hi"]) + 1))
            this_sigma = float(rng.uniform(jitter["sigma_lo"], jitter["sigma_hi"]))
            this_stroke = int(rng.integers(int(jitter["stroke_lo"]), int(jitter["stroke_hi"]) + 1))
            dst_lo = float(rng.uniform(jitter["dst_lo_lo"], jitter["dst_lo_hi"]))
            dst_hi = float(rng.uniform(jitter["dst_hi_lo"], jitter["dst_hi_hi"]))
            this_contrast = (contrast[0], contrast[1], dst_lo, dst_hi) if contrast is not None else None
        if this_side is not None:
            image = _resize_square(image, this_side)
        if this_sigma > 0:
            image = cv2.GaussianBlur(image, (0, 0), this_sigma)
        image = _apply_stroke(image, this_stroke)
        if this_contrast is not None:
            image = _apply_contrast(image, *this_contrast)
        out.append(image)
    return out


def _csv_write(path: Path, rows: list[dict[str, object]]) -> None:
    fields = ["block", "name", "stat", "value", "ci95_lo", "ci95_hi", "n"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _feature_table(name: str, rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    return {feature: quantiles([row[feature] for row in rows]) for feature in FEATURE_NAMES}


def score_manual(rows, preds) -> dict[str, object] | None:
    path = gold_dir() / "glyphs_real_manual.json"
    if not path.is_file():
        return None
    manual = json.loads(path.read_text(encoding="utf-8"))
    by_path = {str(item["path"]): item for item in manual["glyphs"]}
    agree = 0
    compared = 0
    not_sign = 0
    usable_gold = []
    usable_pred = []
    both_gold = []
    both_pred = []
    for row, pred in zip(rows, preds):
        item = by_path[str(row["crop"])]
        if item.get("manual_ok") is False:
            not_sign += 1
            continue
        role = item.get("manual_role")
        if not role:
            continue
        compared += 1
        agree += int(role == row["role"])
        usable_gold.append(str(role))
        usable_pred.append(pred)
        if role == row["role"]:
            both_gold.append(str(role))
            both_pred.append(pred)
    return {
        "agreement": proportion(agree, compared),
        "not_a_sign": proportion(not_sign, len(rows)),
        "manual_top1": _acc_block(usable_gold, usable_pred)["top1"] if usable_gold else None,
        "manual_top5": _acc_block(usable_gold, usable_pred)["top5"] if usable_gold else None,
        "agreed_subset_top1": _acc_block(both_gold, both_pred)["top1"] if both_gold else None,
        "h1_confirmed": bool(compared and agree / compared < 0.85),
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="P5.0b диагностика, без обучения.").parse_args(argv)
    rows = _load_real()
    crops = [to_gray(gold_dir() / str(row["crop"]).split("data/gold/", 1)[-1]) for row in rows]
    norms = [prepare_crop(crop, PrepConfig()) for crop in crops]
    real_feat = [crop_features(crop, norm) for crop, norm in zip(crops, norms)]
    model, charset, device = load_glyph_recognizer(weights_dir())
    if tuple(charset) != ROLE_IDS:
        raise SystemExit(f"charset drift: {charset}")
    preds = _predict(norms, model, charset, device)
    transferred = [str(row["role"]) for row in rows]
    transferred_acc = _acc_block(transferred, preds)
    geo = geometry_report(rows)
    dest = _diag_dir()
    _contact_sheet(rows, crops, norms, preds, dest / "crops_a.png")
    _hist_png(
        {
            "w_src": [item["w_src"] for item in real_feat],
            "stroke_src": [item["stroke_src"] for item in real_feat],
            "stroke_norm": [item["stroke_norm"] for item in real_feat],
            "eff_scale": [item["eff_scale"] for item in real_feat],
            "contrast": [item["contrast"] for item in real_feat],
        },
        dest / "real_feature_hists.png",
    )
    print("EMNIST sample…", flush=True)
    emnist_tiles, emnist_labels, emnist_index = _load_emnist(N_EMNIST)
    # EMNIST tiles are already 28x28. Source size for the NIST scan is 128;
    # w_src here is the ink width on that 28 canvas, and eff_scale uses 128/w_norm
    # only in the comparison note. Feature rows use the 28 image as the array
    # we actually have: w_src = tile width 28, plus ink width.
    emnist_feat = [crop_features(tile, tile) for tile in emnist_tiles]
    for feat in emnist_feat:
        feat["w_src_nist"] = float(NIST_SOURCE)
        feat["eff_scale_vs_nist"] = float(NIST_SOURCE) / max(feat["w_norm"], 1.0)
    real_q = _feature_table("real", real_feat)
    emnist_q = _feature_table("emnist", emnist_feat)
    w_src_med = real_q["w_src"]["median"]
    side = max(4, int(round(28 * w_src_med / NIST_SOURCE)))
    calib = emnist_tiles[:200]
    real_norms_calib = norms[: min(200, len(norms))]
    sigma = _match_blur(real_norms_calib, calib)
    blurred = _degrade(calib, side=side, sigma=sigma, stroke=0, contrast=None, jitter=None, rng=None)
    stroke = _match_stroke(blurred, real_q["stroke_norm"]["median"])
    src_lo, src_hi = _ink_range(emnist_tiles[:400])
    dst_lo, dst_hi = _ink_range(norms)
    contrast = (src_lo, src_hi, dst_lo, dst_hi)
    print(
        f"ladder params side={side} sigma={sigma:.2f} stroke={stroke} contrast={dst_lo:.1f}-{dst_hi:.1f}",
        flush=True,
    )
    rng = np.random.default_rng(SEED)
    jitter = {
        "side_lo": max(4, int(round(28 * real_q["w_src"]["p10"] / NIST_SOURCE))),
        "side_hi": max(5, int(round(28 * real_q["w_src"]["p90"] / NIST_SOURCE))),
        "sigma_lo": max(0.2, sigma * 0.5),
        "sigma_hi": max(sigma, sigma * 1.5, 0.4),
        "stroke_lo": min(0, stroke) - 1,
        "stroke_hi": max(0, stroke) + 1,
        "dst_lo_lo": max(0.0, dst_lo - 15),
        "dst_lo_hi": min(255.0, dst_lo + 15),
        "dst_hi_lo": max(0.0, dst_hi - 15),
        "dst_hi_hi": min(255.0, dst_hi + 15),
    }
    variants = {
        "B0": _degrade(emnist_tiles, side=None, sigma=0.0, stroke=0, contrast=None, jitter=None, rng=None),
        "B1": _degrade(emnist_tiles, side=side, sigma=0.0, stroke=0, contrast=None, jitter=None, rng=None),
        "B2": _degrade(emnist_tiles, side=side, sigma=sigma, stroke=0, contrast=None, jitter=None, rng=None),
        "B3": _degrade(emnist_tiles, side=side, sigma=sigma, stroke=stroke, contrast=None, jitter=None, rng=None),
        "B4": _degrade(emnist_tiles, side=side, sigma=sigma, stroke=stroke, contrast=contrast, jitter=None, rng=None),
        "B5": _degrade(
            emnist_tiles, side=side, sigma=sigma, stroke=stroke, contrast=contrast, jitter=jitter, rng=rng
        ),
    }
    ladder = {}
    b0_preds = None
    for name, tiles in variants.items():
        pred = _predict(tiles, model, charset, device)
        block = _acc_block(emnist_labels, pred)
        ladder[name] = block
        if name == "B0":
            b0_preds = pred
        print(
            f"{name} top1={block['top1']['p']:.3f} [{block['top1']['ci95_lo']:.3f},{block['top1']['ci95_hi']:.3f}] "
            f"top5={block['top5']['p']:.3f}",
            flush=True,
        )
    if b0_preds is None or float(ladder["B0"]["top1"]["p"]) < 0.95:
        raise SystemExit("стоп: demo-путь на недеградированном EMNIST ушёл от 0.975")
    manual = score_manual(rows, preds)
    b5 = float(ladder["B5"]["top1"]["p"])
    b1 = float(ladder["B1"]["top1"]["p"])
    if b1 < 0.35:
        h2 = "H2: виновато разрешение, B1 top1 < 0.35."
    elif b5 >= 0.60:
        h2 = f"H2 опровергнута: B5 top1={b5:.3f} >= 0.60, штрих/контраст/разрешение EMNIST не роняют."
    elif float(ladder["B3"]["top1"]["p"]) < 0.35 or float(ladder["B4"]["top1"]["p"]) < 0.35:
        h2 = "H2: виноваты штрих или контраст, B3/B4 top1 < 0.35 при живом B1."
    else:
        h2 = f"H2 не разобрана одной ступенью: B1={b1:.3f}, B5={b5:.3f}."
    if manual and manual["h1_confirmed"]:
        agree = float(manual["agreement"]["p"])
        verdict = (
            f"Обе, но чинить сначала H1. Согласие transferred/manual={agree:.3f} < 0.85, "
            "прошлые per-glyph числа недействительны. "
            + h2
            + " Новые листы с тем же переносом по числу компонент повторят порчу эталона."
        )
    elif manual is not None:
        verdict = f"H1 не подтверждена (согласие >= 0.85). {h2}"
    else:
        verdict = h2
    report = {
        "trained_epochs": 0,
        "real_crops_used_as_training_labels": False,
        "n_real": len(rows),
        "n_emnist": len(emnist_tiles),
        "seed": SEED,
        "emnist_indices_head": emnist_index[:20],
        "transferred_top1": transferred_acc["top1"],
        "transferred_top5": transferred_acc["top5"],
        "geometry": {key: value for key, value in geo.items() if key != "cells"},
        "geometry_cells": geo["cells"],
        "real_quantiles": real_q,
        "emnist_quantiles": emnist_q,
        "compare": {
            "real_stroke_norm_median": real_q["stroke_norm"]["median"],
            "emnist_stroke_norm_median": emnist_q["stroke_norm"]["median"],
            "real_eff_scale_median": real_q["eff_scale"]["median"],
            "emnist_eff_scale_median": emnist_q["eff_scale"]["median"],
            "real_w_src_median": w_src_med,
            "nist_nominal_source_px": NIST_SOURCE,
            "resolution_side_px": side,
            "formula": "side = round(28 * median(w_src) / 128), then scaled back to 28",
        },
        "ladder_params": {
            "side": side,
            "sigma": sigma,
            "stroke_radius": stroke,
            "contrast_src": [src_lo, src_hi],
            "contrast_dst": [dst_lo, dst_hi],
            "jitter": jitter,
        },
        "ladder": ladder,
        "manual": manual,
        "verdict": verdict,
        "hand_c_allowed": b5 < 0.35,
    }
    (dest / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_rows: list[dict[str, object]] = []
    for domain, table in (("real", real_q), ("emnist", emnist_q)):
        for feature, stats in table.items():
            for stat in ("min", "p10", "median", "p90", "max"):
                csv_rows.append(
                    {"block": domain, "name": feature, "stat": stat, "value": stats[stat], "n": stats["n"]}
                )
    for name, block in ladder.items():
        for metric in ("top1", "top5"):
            item = block[metric]
            csv_rows.append(
                {
                    "block": "ladder",
                    "name": name,
                    "stat": metric,
                    "value": item["p"],
                    "ci95_lo": item["ci95_lo"],
                    "ci95_hi": item["ci95_hi"],
                    "n": item["n"],
                }
            )
    csv_rows.append(
        {
            "block": "transferred",
            "name": "real59",
            "stat": "top1",
            "value": transferred_acc["top1"]["p"],
            "ci95_lo": transferred_acc["top1"]["ci95_lo"],
            "ci95_hi": transferred_acc["top1"]["ci95_hi"],
            "n": transferred_acc["top1"]["n"],
        }
    )
    if manual is not None:
        for name in ("agreement", "not_a_sign", "manual_top1", "agreed_subset_top1"):
            item = manual.get(name)
            if not isinstance(item, dict) or "p" not in item:
                continue
            csv_rows.append(
                {
                    "block": "manual",
                    "name": name,
                    "stat": "p",
                    "value": item["p"],
                    "ci95_lo": item["ci95_lo"],
                    "ci95_hi": item["ci95_hi"],
                    "n": item["n"],
                }
            )
    _csv_write(project_root() / "output" / "ocr_runs" / "p5_diag.csv", csv_rows)
    print(verdict, flush=True)
    print(f"report={dest / 'report.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
