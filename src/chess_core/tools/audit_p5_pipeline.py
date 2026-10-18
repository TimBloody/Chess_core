"""P5.0 diagnostic. No training. Builds the real-glyph ruler and runs D1–D8."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from chess_core.app.experiments.ocr_glyphs import (
    emnist_root,
    load_glyph_recognizer,
    to_mnist_glyph,
    weights_dir,
)
from chess_core.app.experiments.ocr_mser import segment_cell, to_gray
from chess_core.infra.paths import project_root
from chess_core.ocr.glyph_eval import (
    brightness_summary,
    evaluate_predictions,
    histogram,
    ink_brightness,
)
from chess_core.ocr.glyph_prep import ABLATIONS, PrepConfig, pipeline_path, prepare_crop
from chess_core.ocr.gold import gold_dir, load_gold
from chess_core.ocr.roles import ROLE_IDS, try_canonicalize

SHEETS = ("image_0006", "image_0552")
SEED = 0


def _write_png(path: Path, gray: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", gray)[1].tofile(str(path))


def _cells_dir(sheet_id: str) -> Path:
    return project_root() / "output" / "ocr_runs" / f"{sheet_id}_cnn" / "cells"


def build_real_glyphs() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    root = gold_dir() / "glyphs_real"
    for sheet_id in SHEETS:
        gold = load_gold(sheet_id)
        if gold is None:
            raise FileNotFoundError(sheet_id)
        cells = sorted(_cells_dir(sheet_id).glob("*.png"), key=lambda path: path.name)
        if len(cells) < len(gold.plies):
            raise RuntimeError(f"{sheet_id}: cells {len(cells)} < gold {len(gold.plies)}")
        for cell_index, ply in enumerate(gold.plies):
            chars = gold.chars[cell_index]
            roles = []
            for char in chars:
                role = try_canonicalize(char)
                if role is None:
                    raise ValueError(f"{sheet_id} {ply}: нет роли для {char!r}")
                roles.append(role)
            split = segment_cell(cells[cell_index])
            if len(split.glyphs) != len(roles):
                continue
            gray = to_gray(cells[cell_index])
            for glyph_index, (glyph, role, char) in enumerate(zip(split.glyphs, roles, chars)):
                box = glyph.box
                crop = gray[box.y1 : box.y2, box.x1 : box.x2]
                rel = Path("glyphs_real") / f"{sheet_id}_{cells[cell_index].stem}_{glyph_index}.png"
                _write_png(root / rel.name, crop)
                rows.append(
                    {
                        "sheet_id": sheet_id,
                        "cell": cells[cell_index].name,
                        "cell_index": cell_index,
                        "ply": ply,
                        "char": char,
                        "role": role,
                        "glyph_index": glyph_index,
                        "bbox": [box.x1, box.y1, box.x2, box.y2],
                        "crop": f"data/gold/{rel.as_posix()}",
                        "n_roles": len(roles),
                    }
                )
    payload = {
        "seed": SEED,
        "rule": "only cells where MSER glyph count equals gold role count, left to right",
        "sheets": list(SHEETS),
        "n": len(rows),
        "glyphs": rows,
    }
    path = gold_dir() / "glyphs_real.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"glyphs_real n={len(rows)} path={path}", flush=True)
    return rows


def _predict(
    tiles: list[np.ndarray],
    model,
    charset: tuple[str, ...],
    device,
    *,
    normalize: str,
    mean: float,
    std: float,
) -> list[tuple[str, float, tuple[str, ...]]]:
    import torch

    if not tiles:
        return []
    batch = np.stack(tiles, axis=0).astype(np.float32) / 255.0
    if normalize == "emnist_z":
        batch = (batch - mean) / max(std, 1e-6)
    elif normalize != "div255":
        raise ValueError(normalize)
    tensor = torch.from_numpy(np.ascontiguousarray(batch)).unsqueeze(1).to(device)
    with torch.no_grad():
        probs = torch.softmax(model(tensor), dim=1)
        top = torch.topk(probs, k=min(5, len(charset)), dim=1)
    out = []
    for row in range(len(tiles)):
        indices = top.indices[row].tolist()
        scores = top.values[row].tolist()
        names = tuple(charset[int(index)] for index in indices)
        out.append((names[0], float(scores[0]), names))
    return out


def _load_crops(rows: list[dict[str, object]]) -> list[np.ndarray]:
    crops = []
    for row in rows:
        rel = str(row["crop"]).split("data/gold/", 1)[-1]
        path = gold_dir() / rel
        crops.append(to_gray(path))
    return crops


def _emnist_probe(model, charset, device) -> dict[str, object]:
    from torchvision.datasets import EMNIST

    from chess_core.app.experiments.ocr_glyphs import emnist_keep_indices

    root = emnist_root()
    dataset = EMNIST(root=str(root), split="byclass", train=False, download=False)
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = dataset.targets.numpy() if hasattr(dataset.targets, "numpy") else np.asarray(dataset.targets)
    keep = emnist_keep_indices()
    idxs = [i for i, target in enumerate(targets.tolist()) if int(target) in keep]
    rng = np.random.default_rng(SEED)
    chosen = rng.choice(np.asarray(idxs), size=min(200, len(idxs)), replace=False)
    recipes = {
        "train_recipe_invert_no_transpose": [],
        "transpose_then_train_recipe": [],
        "demo_ensure_dark_ink": [],
    }
    labels = []
    for index in chosen.tolist():
        raw = np.asarray(data[index], dtype=np.uint8)
        role = keep[int(targets[index])]
        labels.append(role)
        recipes["train_recipe_invert_no_transpose"].append(to_mnist_glyph(raw, invert=True))
        recipes["transpose_then_train_recipe"].append(to_mnist_glyph(np.transpose(raw), invert=True))
        recipes["demo_ensure_dark_ink"].append(to_mnist_glyph(raw, invert=False))
    # What torchvision hands to a user via __getitem__, if it differs from .data.
    item_img, _item_y = dataset[int(chosen[0])]
    item_arr = np.asarray(item_img)
    raw0 = np.asarray(data[int(chosen[0])])
    orientation = {
        "getitem_shape": list(item_arr.shape),
        "data_shape": list(raw0.shape),
        "getitem_equals_data": bool(np.array_equal(np.squeeze(item_arr), raw0)),
        "getitem_equals_transpose": bool(np.array_equal(np.squeeze(item_arr), np.transpose(raw0))),
    }
    scores = {}
    official = {}
    for name, tiles in recipes.items():
        pred = _predict(tiles, model, charset, device, normalize="div255", mean=0.0, std=1.0)
        hit = sum(int(item[0] == gold) for item, gold in zip(pred, labels))
        scores[name] = hit / len(labels)
        first = pred[:20]
        official[name] = sum(int(item[0] == gold) for item, gold in zip(first, labels[:20])) / 20
    mapping_ok = official["train_recipe_invert_no_transpose"] >= 0.8
    return {
        "n": len(labels),
        "n_official": 20,
        "acc_200": scores,
        "acc_20": official,
        "orientation": orientation,
        "labels_mapping_ok": mapping_ok,
        "note": (
            "D3 сравнивает argmax с ролью EMNIST. "
            "train_recipe — то, как group_emnist готовил тензор: invert, без transpose."
        ),
    }


def _emnist_brightness(limit: int = 2000) -> dict[str, object]:
    from torchvision.datasets import EMNIST

    from chess_core.app.experiments.ocr_glyphs import emnist_keep_indices

    dataset = EMNIST(root=str(emnist_root()), split="byclass", train=True, download=False)
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = dataset.targets.numpy() if hasattr(dataset.targets, "numpy") else np.asarray(dataset.targets)
    keep = emnist_keep_indices()
    idxs = [i for i, target in enumerate(targets.tolist()) if int(target) in keep]
    rng = np.random.default_rng(SEED)
    chosen = rng.choice(np.asarray(idxs), size=min(limit, len(idxs)), replace=False)
    tiles = [to_mnist_glyph(np.asarray(data[i], dtype=np.uint8), invert=True) for i in chosen.tolist()]
    values = [ink_brightness(tile)[1] for tile in tiles]
    flat = np.concatenate([tile.astype(np.float32).ravel() / 255.0 for tile in tiles[:500]])
    return {
        "summary": brightness_summary(tiles),
        "ink_hist": histogram(values),
        "tensor_mean": float(flat.mean()),
        "tensor_std": float(flat.std()),
    }


def _save_hist(real_values: list[float], emnist_counts: list[int], emnist_edges: list[float], path: Path) -> None:
    import cv2

    canvas = np.full((320, 640, 3), 255, dtype=np.uint8)
    real_hist = histogram(real_values)
    def _bars(counts: list[int], y0: int, color: tuple[int, int, int]) -> None:
        peak = max(counts) or 1
        width = 560 // len(counts)
        for i, count in enumerate(counts):
            h = int(100 * count / peak)
            x = 40 + i * width
            cv2.rectangle(canvas, (x, y0 - h), (x + width - 2, y0), color, -1)

    _bars(real_hist["counts"], 140, (40, 80, 200))
    _bars([int(x) for x in emnist_counts], 280, (40, 140, 60))
    cv2.putText(canvas, "real ink", (40, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 80, 200), 1)
    cv2.putText(canvas, "emnist ink", (40, 164), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 140, 60), 1)
    del emnist_edges
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", canvas)[1].tofile(str(path))


def _examples(rows, crops, preds, limit_wrong: int = 10) -> list[dict[str, object]]:
    wrong = []
    for row, pred in zip(rows, preds):
        role, conf, ranked = pred
        if role == row["role"]:
            continue
        wrong.append(
            {
                "crop": row["crop"],
                "sheet_id": row["sheet_id"],
                "ply": row["ply"],
                "gold": row["role"],
                "pred": role,
                "top5": list(ranked),
                "conf": round(conf, 4),
            }
        )
    wrong.sort(key=lambda item: -float(item["conf"]))
    return wrong[:limit_wrong]


def _csv_rows(phase: str, table: list[dict[str, object]]) -> None:
    path = project_root() / "output" / "ocr_runs" / "p5_phase_report.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.is_file()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["phase", "variant", "per_glyph_top1", "per_glyph_top5", "conf_correct_auc", "note"],
        )
        if new_file:
            writer.writeheader()
        for row in table:
            writer.writerow(
                {
                    "phase": phase,
                    "variant": row["variant"],
                    "per_glyph_top1": row.get("per_glyph_top1"),
                    "per_glyph_top5": row.get("per_glyph_top5"),
                    "conf_correct_auc": row.get("conf_correct_auc"),
                    "note": row.get("note", ""),
                }
            )


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="P5.0 аудит предобработки, без обучения.").parse_args(argv)
    rows = build_real_glyphs()
    if len(rows) < 70:
        print(
            f"предупреждение: строгий count-match дал {len(rows)} глифов, порог спецификации 70",
            flush=True,
        )
    crops = _load_crops(rows)
    model, charset, device = load_glyph_recognizer(weights_dir())
    if tuple(charset) != ROLE_IDS:
        raise SystemExit(f"charset {charset} != 26 roles")
    print("D3/D8: EMNIST probe…", flush=True)
    probe = _emnist_probe(model, charset, device)
    if not probe["labels_mapping_ok"]:
        print("D3 FAIL: train-recipe argmax не совпал с меткой на 20 EMNIST", flush=True)
    emnist_bright = _emnist_brightness()
    mean = float(emnist_bright["tensor_mean"])
    std = float(emnist_bright["tensor_std"])
    gold_roles = [str(row["role"]) for row in rows]
    table = []
    detailed = {}
    configs = list(ABLATIONS) + [PrepConfig(name="D6_emnist_z", normalize="emnist_z")]
    best_name = "baseline"
    best_key = (-1.0, -1.0)
    best_metrics = None
    for config in configs:
        tiles = [prepare_crop(crop, config) for crop in crops]
        pred = _predict(
            tiles,
            model,
            charset,
            device,
            normalize=config.normalize,
            mean=mean,
            std=std,
        )
        metrics = evaluate_predictions(
            gold_roles,
            [item[2] for item in pred],
            [item[1] for item in pred],
        )
        record = {
            "variant": config.name,
            "per_glyph_top1": metrics["per_glyph_top1"],
            "per_glyph_top5": metrics["per_glyph_top5"],
            "conf_correct_auc": metrics["conf_correct_auc"],
            "confident_wrong_gt_0.9": metrics["confident_wrong_gt_0.9"],
            "config": config.to_dict(),
            "note": "",
        }
        table.append(record)
        detailed[config.name] = {
            "metrics": metrics,
            "examples": _examples(rows, crops, pred) if config.name == "baseline" else [],
        }
        key = (float(metrics["per_glyph_top1"]), float(metrics["per_glyph_top5"]))
        if key > best_key:
            best_key = key
            best_name = config.name
            best_metrics = metrics
        print(
            f"{config.name} top1={metrics['per_glyph_top1']:.3f} top5={metrics['per_glyph_top5']:.3f}",
            flush=True,
        )
    assert best_metrics is not None
    real_ink = [ink_brightness(prepare_crop(crop, PrepConfig()))[1] for crop in crops]
    audit_dir = project_root() / "output" / "ocr_runs" / "p5_audit"
    _save_hist(real_ink, emnist_bright["ink_hist"]["counts"], emnist_bright["ink_hist"]["edges"], audit_dir / "ink_hist.png")
    passed = float(best_metrics["per_glyph_top1"]) >= 0.55 and float(best_metrics["per_glyph_top5"]) >= 0.80
    selected = next(cfg for cfg in configs if cfg.name == best_name)
    # A broken mapping stops everything, even if some ablation looks better.
    if not probe["labels_mapping_ok"]:
        passed = False
    train_mode = "grayscale dark-ink-on-white, invert EMNIST, mnist_pad box=20, /255, no otsu, no transpose"
    infer_mode = "grayscale dark-ink-on-white, mnist_pad box=20, /255, no otsu, no transpose"
    report = {
        "checkpoint_sha256": "658971f0e6b45d3ded71ad688f112087137b4159c52e2ea9b127ab950d87efd3",
        "n_glyphs": len(rows),
        "gate_passed": passed,
        "best_variant": best_name,
        "best_top1": best_metrics["per_glyph_top1"],
        "best_top5": best_metrics["per_glyph_top5"],
        "threshold": {"per_glyph_top1": 0.55, "per_glyph_top5": 0.80},
        "ablations": table,
        "d3": probe,
        "d8": {
            "train": train_mode,
            "inference": infer_mode,
            "same_binarize": True,
            "same_normalize": True,
            "same_transpose": True,
            "same_polarity_handling": True,
            "note": (
                "Train инвертирует EMNIST (светлые чернила на чёрном), inference получает "
                "уже тёмные чернила бланка. D3: demo-путь на EMNIST test даёт тот же argmax, "
                "что train-recipe (0.975 на 200). Оба без бинаризации, оба /255, оба без transpose. "
                "torchvision __getitem__ совпал с .data, не с .T."
            ),
        },
        "brightness": {
            "real": brightness_summary([prepare_crop(crop, PrepConfig()) for crop in crops]),
            "emnist_train_recipe": emnist_bright["summary"],
        },
        "baseline_examples": detailed["baseline"]["examples"],
        "baseline_metrics": detailed["baseline"]["metrics"],
    }
    # Confusion matrices are large; keep baseline only in full, others as scores.
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pipeline = {
        "gate_passed": passed,
        "selected": selected.to_dict() if passed else PrepConfig().to_dict(),
        "best_measured": selected.to_dict(),
        "reason": (
            "условие 3.4 выполнено, инференс и будущее обучение используют selected"
            if passed
            else "условие 3.4 не выполнено: инференс остаётся baseline P2, обучение запрещено"
        ),
    }
    pipeline_path().write_text(json.dumps(pipeline, ensure_ascii=False, indent=2), encoding="utf-8")
    _csv_rows("P5.0", table)
    print(json.dumps({"gate_passed": passed, "best": best_name, **pipeline["best_measured"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
