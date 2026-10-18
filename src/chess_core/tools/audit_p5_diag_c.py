"""P5.0c: is the glyph still in the 28x28 tensor the network sees?

No training. The answer is human_top1_28, with a Wilson interval.
Sheets carry an anonymous id and the pixels only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from chess_core.app.experiments.ocr_glyphs import (
    emnist_keep_indices,
    emnist_root,
    load_glyph_recognizer,
    to_mnist_glyph,
    weights_dir,
)
from chess_core.app.experiments.ocr_mser import to_gray
from chess_core.infra.paths import project_root
from chess_core.ocr.blind_sheet import render_blind_sheet, shuffled_indices, spearman
from chess_core.ocr.diag_stats import proportion
from chess_core.ocr.glyph_eval import roc_auc
from chess_core.ocr.glyph_prep import PrepConfig, prepare_crop
from chess_core.ocr.gold import gold_dir
from chess_core.ocr.roles import ROLE_BY_ID, ROLE_IDS

# Written before any blind label exists. Do not retune after seeing the number.
# human_top1_28 = share of raw-readable crops whose pad28 role equals the raw role.
# pad28 readable=false or a different role is a miss. Transferred labels are not the gold.
#   >= 0.85 informative (style gap; real data is the next step)
#   0.60 .. 0.85 partial (keep only what a human can read)
#   < 0.60 destroyed (fix the crop / prep before collecting sheets)
RULE_INFORMATIVE = 0.85
RULE_PARTIAL = 0.60

_BLIND_META: dict[str, str] = {"method": ""}

SEED_RAW = 501
SEED_PAD = 502
SEED_X4 = 503
N_EMNIST = 2000
MIN_SIDE = 96


def _write_png(path: Path, image: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"png encode failed: {path}")
    encoded.tofile(str(path))


def _read_png(path: Path) -> np.ndarray:
    return to_gray(path)


def _out_dir() -> Path:
    path = project_root() / "output" / "ocr_runs" / "p5_diag_c"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_rows() -> list[dict[str, object]]:
    payload = json.loads((gold_dir() / "glyphs_real.json").read_text(encoding="utf-8"))
    rows = list(payload["glyphs"])
    if len(rows) != 59:
        raise RuntimeError(f"expected 59 real glyphs, got {len(rows)}")
    return rows


def _grid(cell: str) -> tuple[int, int]:
    stem = Path(cell).stem
    row = int(stem.split("_r")[1].split("_")[0])
    col = int(stem.split("_c")[1])
    return row, col


def anonymous_id(index: int) -> str:
    return f"g{index + 1:03d}"


def _nearest(gray: np.ndarray, scale: int) -> np.ndarray:
    import cv2

    if scale <= 1:
        return np.ascontiguousarray(gray)
    height, width = gray.shape[:2]
    return cv2.resize(gray, (width * scale, height * scale), interpolation=cv2.INTER_NEAREST)


def _min_side(gray: np.ndarray, min_side: int) -> np.ndarray:
    height, width = gray.shape[:2]
    scale = max(1, math.ceil(min_side / max(min(height, width), 1)))
    return _nearest(gray, scale)


def _pages(images: list[np.ndarray], ids: list[str], dest: Path, *, per_page: int = 6) -> None:
    if dest.exists():
        for old in dest.glob("*.png"):
            old.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(images), per_page):
        canvas, captions = render_blind_sheet(images[start : start + per_page], ids[start : start + per_page], cols=2)
        if any(not item.startswith("g") for item in captions):
            raise RuntimeError("page caption leaked")
        _write_png(dest / f"page_{start // per_page:02d}.png", canvas)


def _emit_sheets(rows: list[dict[str, object]]) -> dict[str, object]:
    crops = [_read_png(gold_dir() / str(row["crop"]).split("data/gold/", 1)[-1]) for row in rows]
    pad28 = [prepare_crop(crop, PrepConfig()) for crop in crops]
    ids = [anonymous_id(i) for i in range(len(rows))]
    levels = {
        "raw": (SEED_RAW, [_min_side(crop, MIN_SIDE) for crop in crops]),
        "pad28": (SEED_PAD, pad28),
        "pad28x4": (SEED_X4, [_nearest(tile, 4) for tile in pad28]),
    }
    dest = _out_dir()
    orders: dict[str, list[str]] = {}
    correlations: dict[str, dict[str, float]] = {}
    for name, (seed, images) in levels.items():
        order_idx = shuffled_indices(len(rows), seed)
        view_ids = [ids[i] for i in order_idx]
        view_images = [images[i] for i in order_idx]
        canvas, captions = render_blind_sheet(view_images, view_ids, cols=4)
        if captions != view_ids:
            raise RuntimeError("sheet captions are not the anonymous ids")
        filename = "crops_blind.png" if name == "raw" else f"sheet_{name}.png"
        _write_png(dest / filename, canvas)
        _pages(view_images, view_ids, dest / f"pages_{name}")
        orders[name] = view_ids
        rows_pos = []
        cols_pos = []
        for position, source in enumerate(order_idx):
            grid_r, grid_c = _grid(str(rows[source]["cell"]))
            rows_pos.append(float(grid_r))
            cols_pos.append(float(grid_c))
        correlations[name] = {
            "spearman_row": spearman(list(range(len(order_idx))), rows_pos),
            "spearman_col": spearman(list(range(len(order_idx))), cols_pos),
        }
    key_items = []
    for index, row in enumerate(rows):
        grid_r, grid_c = _grid(str(row["cell"]))
        key_items.append(
            {
                "id": ids[index],
                "path": row["crop"],
                "sheet_id": row["sheet_id"],
                "cell": row["cell"],
                "row": grid_r,
                "col": grid_c,
                "transferred_role": row["role"],
                "source_index": index,
            }
        )
    key = {
        "note": "mapping for scoring only; not shown on the sheets",
        "orders": orders,
        "correlations": correlations,
        "items": key_items,
    }
    (dest / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    ink_widths = []
    for tile in pad28:
        ink = tile < 175
        if not np.any(ink):
            ink_widths.append(0.0)
            continue
        xs = np.where(ink)[1]
        ink_widths.append(float(int(xs.max()) - int(xs.min()) + 1))
    return {
        "n": len(rows),
        "correlations": correlations,
        "ink_width_on_28": {
            "median": float(np.median(ink_widths)),
            "box": 20,
        },
        "sheets": {
            "raw": str((dest / "crops_blind.png").relative_to(project_root())),
            "pad28": str((dest / "sheet_pad28.png").relative_to(project_root())),
            "pad28x4": str((dest / "sheet_pad28x4.png").relative_to(project_root())),
        },
    }


def _load_blind() -> dict[str, list[dict[str, object]]] | None:
    path = gold_dir() / "glyphs_real_blind.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    _BLIND_META["method"] = str(payload.get("method") or "")
    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise RuntimeError("glyphs_real_blind.json needs levels.raw / pad28 / pad28x4")
    return {str(name): list(rows) for name, rows in levels.items()}


def _by_id(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        gid = str(row["id"])
        if gid in out:
            raise RuntimeError(f"duplicate blind id {gid}")
        out[gid] = row
    return out


def _role_of(row: dict[str, object] | None) -> str | None:
    if row is None or row.get("readable") is not True:
        return None
    role = row.get("role")
    if role is None or role == "":
        return None
    text = str(role)
    if text not in ROLE_IDS:
        raise RuntimeError(f"unknown role {text}")
    return text


def _agree(left: dict[str, dict[str, object]], right: dict[str, dict[str, object]], ids: list[str]) -> dict[str, object]:
    hits = 0
    compared = 0
    for gid in ids:
        a = _role_of(left.get(gid))
        b = _role_of(right.get(gid))
        if a is None or b is None:
            continue
        compared += 1
        hits += int(a == b)
    block = proportion(hits, compared)
    block["skipped_unreadable"] = len(ids) - compared
    return block


def _human_recovery(reference: dict[str, dict[str, object]], other: dict[str, dict[str, object]], ids: list[str]) -> dict[str, object]:
    """Match `other` to a readable reference. Unreadable `other` is a miss."""

    hits = 0
    denominator = 0
    for gid in ids:
        gold = _role_of(reference.get(gid))
        if gold is None:
            continue
        denominator += 1
        hits += int(_role_of(other.get(gid)) == gold)
    return proportion(hits, denominator)


def _verdict(human_28: dict[str, object]) -> str:
    p = float(human_28["p"])
    n = int(human_28["n"])
    lo = float(human_28["ci95_lo"])
    hi = float(human_28["ci95_hi"])
    point = _bucket(p)
    span = _bucket(lo) != _bucket(hi)
    ci = f"human_top1_28={p:.3f} (n={n}, 95% ДИ {lo:.3f}–{hi:.3f})"
    if span:
        return (
            f"Порог не разделён: {ci}. Точечная оценка в зоне «{_BUCKET_RU[point]}», "
            f"интервал тянется от «{_BUCKET_RU[_bucket(lo)]}» до «{_BUCKET_RU[_bucket(hi)]}». "
            "Сбор листов следующим шагом не объявляется."
        )
    if point == "informative":
        return f"Вход информативен: {ci}. Сбор реальных данных оправдан как следующий шаг."
    if point == "partial":
        return (
            f"Вход частично разрушен: {ci}. "
            "Дальше только читаемые кропы; сплошной сбор листов не оправдан."
        )
    return (
        f"Вход уничтожает глиф: {ci}. "
        "Следующий шаг — кроп и предобработка, не сбор листов."
    )


def _bucket(p: float) -> str:
    if p >= RULE_INFORMATIVE:
        return "informative"
    if p >= RULE_PARTIAL:
        return "partial"
    return "destroyed"


_BUCKET_RU = {
    "informative": "информативен",
    "partial": "частично разрушен",
    "destroyed": "уничтожен",
}


def _predict(tiles: list[np.ndarray], model, charset: tuple[str, ...], device) -> list[tuple[str, float, tuple[str, ...]]]:
    import torch

    out: list[tuple[str, float, tuple[str, ...]]] = []
    if not tiles:
        return out
    for start in range(0, len(tiles), 256):
        batch = np.stack(tiles[start : start + 256], axis=0).astype(np.float32) / 255.0
        tensor = torch.from_numpy(np.ascontiguousarray(batch)).unsqueeze(1).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(tensor), dim=1)
            top = torch.topk(probs, k=min(5, len(charset)), dim=1)
        for row in range(batch.shape[0]):
            names = tuple(charset[int(i)] for i in top.indices[row].tolist())
            out.append((names[0], float(top.values[row, 0]), names))
    return out


def _load_emnist(n: int) -> tuple[list[np.ndarray], list[str]]:
    from torchvision.datasets import EMNIST

    dataset = EMNIST(root=str(emnist_root()), split="byclass", train=False, download=False)
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = dataset.targets.numpy() if hasattr(dataset.targets, "numpy") else np.asarray(dataset.targets)
    keep = emnist_keep_indices()
    idxs = np.asarray([i for i, target in enumerate(targets.tolist()) if int(target) in keep], dtype=np.int64)
    rng = np.random.default_rng(0)
    chosen = rng.choice(idxs, size=min(n, len(idxs)), replace=False)
    tiles = []
    labels = []
    for index in chosen.tolist():
        raw = np.asarray(data[index], dtype=np.uint8)
        tiles.append(to_mnist_glyph(raw, invert=True))
        labels.append(keep[int(targets[index])])
    return tiles, labels


def _top_share(names: list[str], k: int = 3) -> dict[str, object]:
    counts = Counter(names)
    top = counts.most_common(k)
    covered = sum(count for _name, count in top)
    block = proportion(covered, len(names))
    block["classes"] = [{"role": name, "n": count} for name, count in top]
    block["collapsed"] = bool(block["p"] > 0.60) if names else False
    return block


def _kind(role: str) -> str:
    return ROLE_BY_ID[role].kind


def _structure(golds: list[str], preds: list[str]) -> dict[str, object]:
    errors = [(gold, pred) for gold, pred in zip(golds, preds) if gold != pred]
    same = sum(int(_kind(gold) == _kind(pred)) for gold, pred in errors)
    chance_hits = 0.0
    for gold, _pred in errors:
        same_kind_others = sum(1 for role in ROLE_IDS if role != gold and _kind(role) == _kind(gold))
        chance_hits += same_kind_others / max(len(ROLE_IDS) - 1, 1)
    pairs = Counter(errors)
    return {
        "n_errors": len(errors),
        "same_kind": proportion(same, len(errors)),
        "chance_same_kind": (chance_hits / len(errors)) if errors else float("nan"),
        "top_confusions": [
            {"gold": gold, "pred": pred, "n": count} for (gold, pred), count in pairs.most_common(8)
        ],
    }


def _hist_png(real_counts: Counter[str], emnist_counts: Counter[str], path: Path) -> None:
    import cv2

    roles = list(ROLE_IDS)
    width = 40 + len(roles) * 28
    height = 280
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    real_n = max(sum(real_counts.values()), 1)
    emnist_n = max(sum(emnist_counts.values()), 1)
    for index, role in enumerate(roles):
        x = 30 + index * 28
        real_h = int(200 * real_counts[role] / real_n)
        emnist_h = int(200 * emnist_counts[role] / emnist_n)
        cv2.rectangle(canvas, (x, 220 - real_h), (x + 10, 220), (40, 80, 180), thickness=-1)
        cv2.rectangle(canvas, (x + 12, 220 - emnist_h), (x + 22, 220), (180, 100, 40), thickness=-1)
    cv2.putText(canvas, "real", (30, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 80, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, "emnist", (100, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 100, 40), 1, cv2.LINE_AA)
    _write_png(path, canvas)


def _score(rows: list[dict[str, object]], sheet_meta: dict[str, object]) -> dict[str, object]:
    levels = _load_blind()
    if levels is None:
        raise RuntimeError("data/gold/glyphs_real_blind.json is missing")
    for name in ("raw", "pad28", "pad28x4"):
        if name not in levels:
            raise RuntimeError(f"blind level {name} missing")
    ids = [anonymous_id(i) for i in range(len(rows))]
    maps = {name: _by_id(levels[name]) for name in ("raw", "pad28", "pad28x4")}
    for name, mapping in maps.items():
        missing = [gid for gid in ids if gid not in mapping]
        if missing:
            raise RuntimeError(f"{name} missing ids: {missing[:5]}")
    raw = maps["raw"]
    pad = maps["pad28"]
    x4 = maps["pad28x4"]
    manual_path = gold_dir() / "glyphs_real_manual.json"
    manual_rows = json.loads(manual_path.read_text(encoding="utf-8"))["glyphs"]
    if len(manual_rows) != len(rows):
        raise RuntimeError("manual json length drift")
    manual = {
        anonymous_id(i): {
            "id": anonymous_id(i),
            "role": row.get("manual_role"),
            "readable": bool(row.get("manual_ok")),
        }
        for i, row in enumerate(manual_rows)
    }
    transferred = {
        anonymous_id(i): {"id": anonymous_id(i), "role": row["role"], "readable": True}
        for i, row in enumerate(rows)
    }
    human_raw = proportion(sum(int(_role_of(raw.get(gid)) is not None) for gid in ids), len(ids))
    human_28 = _human_recovery(raw, pad, ids)
    human_x4 = _human_recovery(raw, x4, ids)
    agreed_ids = [
        gid
        for gid in ids
        if _role_of(raw.get(gid)) is not None
        and _role_of(raw.get(gid)) == _role_of(pad.get(gid)) == _role_of(x4.get(gid))
    ]
    crops = [_read_png(gold_dir() / str(row["crop"]).split("data/gold/", 1)[-1]) for row in rows]
    tiles = {
        "margin0": [prepare_crop(crop, PrepConfig(margin=0, box=20)) for crop in crops],
        "margin2": [prepare_crop(crop, PrepConfig(margin=2, box=20)) for crop in crops],
        "margin4": [prepare_crop(crop, PrepConfig(margin=4, box=20)) for crop in crops],
        "margin8": [prepare_crop(crop, PrepConfig(margin=8, box=20)) for crop in crops],
        "box16": [prepare_crop(crop, PrepConfig(box=16)) for crop in crops],
        "box20": [prepare_crop(crop, PrepConfig(box=20)) for crop in crops],
        "box24": [prepare_crop(crop, PrepConfig(box=24)) for crop in crops],
    }
    cell_cache: dict[tuple[str, str], np.ndarray] = {}
    tight_tiles = []
    for row in rows:
        key = (str(row["sheet_id"]), str(row["cell"]))
        if key not in cell_cache:
            cell_path = project_root() / "output" / "ocr_runs" / f"{row['sheet_id']}_cnn" / "cells" / str(row["cell"])
            cell_cache[key] = prepare_crop(_read_png(cell_path), PrepConfig())
        tight_tiles.append(cell_cache[key])
    tiles["cell"] = tight_tiles

    model, charset, device = load_glyph_recognizer(weights_dir())
    if tuple(charset) != ROLE_IDS:
        raise SystemExit(f"charset drift: {charset}")
    preds = {name: _predict(batch, model, charset, device) for name, batch in tiles.items()}
    readable_index = [i for i, gid in enumerate(ids) if _role_of(pad.get(gid)) is not None]
    readable_gold = [_role_of(pad[ids[i]]) for i in readable_index]
    assert all(item is not None for item in readable_gold)

    def acc_on(name: str) -> dict[str, object]:
        chosen = [preds[name][i] for i in readable_index]
        golds = [str(item) for item in readable_gold]
        top1 = sum(int(pred[0] == gold) for gold, pred in zip(golds, chosen))
        top5 = sum(int(gold in pred[2][:5]) for gold, pred in zip(golds, chosen))
        return {"top1": proportion(top1, len(golds)), "top5": proportion(top5, len(golds))}

    ablations = {name: acc_on(name) for name in tiles}
    base_preds = preds["box20"]
    net_preds = [base_preds[i] for i in readable_index]
    net_golds = [str(item) for item in readable_gold]
    net_top1 = proportion(sum(int(pred[0] == gold) for gold, pred in zip(net_golds, net_preds)), len(net_golds))
    agreed_set = set(agreed_ids)
    agreed_index = [i for i, gid in enumerate(ids) if gid in agreed_set]
    agreed_golds = [str(_role_of(raw[ids[i]])) for i in agreed_index]
    agreed_preds = [base_preds[i] for i in agreed_index]
    net_on_agreed = proportion(
        sum(int(pred[0] == gold) for gold, pred in zip(agreed_golds, agreed_preds)),
        len(agreed_golds),
    )
    correct = [int(pred[0] == gold) for gold, pred in zip(net_golds, net_preds)]
    conf = [pred[1] for pred in net_preds]
    real_names = [pred[0] for pred in base_preds]
    print("EMNIST prior…", flush=True)
    emnist_tiles, _emnist_labels = _load_emnist(N_EMNIST)
    emnist_preds = _predict(emnist_tiles, model, charset, device)
    emnist_names = [pred[0] for pred in emnist_preds]
    dest = _out_dir()
    _hist_png(Counter(real_names), Counter(emnist_names), dest / "pred_hist.png")
    unreadable = proportion(sum(int(_role_of(raw.get(gid)) is None) for gid in ids), len(ids))
    blind_vs_transferred = _agree(raw, transferred, ids)
    blind_vs_manual = _agree(raw, manual, ids)
    manual_anchored = bool(
        blind_vs_manual["n"]
        and abs(float(blind_vs_manual["p"]) - 1.0) > 0.15
    )
    report: dict[str, object] = {
        "step": "P5.0c",
        "labeler": _BLIND_META["method"],
        "trained_epochs": 0,
        "real_crops_used_as_training_labels": False,
        "p5_closed": False,
        "definition": (
            "human_top1_raw — доля кропов, которым на raw присвоена роль (читаемость фото). "
            "human_top1_28 — доля кропов с читаемым raw, на которых роль pad28 совпала с ролью raw; "
            "нечитаемый pad28 считается промахом. human_top1_28x4 — то же для nearest x4. "
            "transferred не эталон: он уже расходится с глазом."
        ),
        "rule_before_numbers": {
            "informative": "human_top1_28 >= 0.85",
            "partial": "0.60 <= human_top1_28 < 0.85",
            "destroyed": "human_top1_28 < 0.60",
        },
        "n_below_100": True,
        "sheets": sheet_meta["sheets"],
        "shuffle_correlation": sheet_meta["correlations"],
        "ink_width_on_28": sheet_meta["ink_width_on_28"],
        "blind_vs_transferred": blind_vs_transferred,
        "blind_vs_manual": blind_vs_manual,
        "manual_p5_0b_unreliable": manual_anchored,
        "raw_unreadable": unreadable,
        "human_top1_raw": human_raw,
        "human_top1_28": human_28,
        "human_top1_28x4": human_x4,
        "levels_agree_n": proportion(len(agreed_ids), len(ids)),
        "net_top1_on_agreed": net_on_agreed,
        "net_top1_on_readable": net_top1,
        "auc_conf_correct_readable": roc_auc(conf, correct) if net_golds else float("nan"),
        "ablations": ablations,
        "prediction_share_top3_real": _top_share(real_names),
        "prediction_share_top3_emnist": _top_share(emnist_names),
        "error_structure_readable": _structure(net_golds, [pred[0] for pred in net_preds]),
        "part_e": "not_run",
        "verdict": _verdict(human_28),
    }
    if float(human_28["p"]) >= RULE_INFORMATIVE and _bucket(float(human_28["ci95_lo"])) == "informative":
        report["part_e"] = "required"
    (dest / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(project_root() / "output" / "ocr_runs" / "p5_diag_c.csv", report)
    print(report["verdict"], flush=True)
    return report


def _write_csv(path: Path, report: dict[str, object]) -> None:
    rows: list[dict[str, object]] = []

    def add(block: str, name: str, item: dict[str, object]) -> None:
        if "p" not in item:
            return
        rows.append(
            {
                "block": block,
                "name": name,
                "p": item.get("p"),
                "ci95_lo": item.get("ci95_lo"),
                "ci95_hi": item.get("ci95_hi"),
                "n": item.get("n"),
                "hits": item.get("hits"),
            }
        )

    for name in (
        "blind_vs_transferred",
        "blind_vs_manual",
        "raw_unreadable",
        "human_top1_raw",
        "human_top1_28",
        "human_top1_28x4",
        "levels_agree_n",
        "net_top1_on_agreed",
        "net_top1_on_readable",
        "prediction_share_top3_real",
        "prediction_share_top3_emnist",
    ):
        item = report[name]
        if isinstance(item, dict):
            add(name, "p", item)
    ablations = report["ablations"]
    if isinstance(ablations, dict):
        for name, block in ablations.items():
            if isinstance(block, dict):
                top1 = block.get("top1")
                top5 = block.get("top5")
                if isinstance(top1, dict):
                    add("ablation_top1", str(name), top1)
                if isinstance(top5, dict):
                    add("ablation_top5", str(name), top5)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["block", "name", "p", "ci95_lo", "ci95_hi", "n", "hits"])
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P5.0c blind ceiling. No training.")
    parser.add_argument("--sheets-only", action="store_true")
    args = parser.parse_args(argv)
    rows = _load_rows()
    meta = _emit_sheets(rows)
    print(
        "sheets",
        meta["sheets"]["raw"],
        "corr",
        {name: {k: round(v, 3) for k, v in corr.items()} for name, corr in meta["correlations"].items()},
        flush=True,
    )
    if args.sheets_only:
        return 0
    if _load_blind() is None:
        print("blind json missing; sheets only", flush=True)
        return 0
    _score(rows, meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
