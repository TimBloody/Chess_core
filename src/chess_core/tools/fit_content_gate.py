"""Fit gate thresholds on TRAIN sheets only. Holdout is scored once at the end."""

from __future__ import annotations

import argparse
import json

import numpy as np

from chess_core.ocr.gate.calibration import (
    binary_pr,
    ece_score,
    operating_point,
    platt_apply,
    platt_fit,
    pr_auc,
    pr_curve_png,
    reliability_png,
)
from chess_core.ocr.gate.catalog import (
    assert_holdout_unused_by_fit,
    assert_sheet_disjoint,
    gate_root,
    holdout_rows,
    load_catalog,
    train_rows,
)
from chess_core.ocr.gate.content import model_path, thresholds_path
from chess_core.ocr.gate.features import FEATURE_NAMES, extract_raw_features, gate_vector
from chess_core.ocr.gate.heuristic import HeuristicGate, HeuristicThresholds, save_thresholds
from chess_core.tools.collect_gate_crops import _read_gray


def _xy(rows, *, with_tile: bool = False) -> tuple[np.ndarray, np.ndarray, list[str]]:
    xs = []
    ys = []
    paths = []
    for row in rows:
        image = _read_gray(gate_root() / row.path)
        if image is None:
            raise FileNotFoundError(row.path)
        vec = gate_vector(image) if with_tile else extract_raw_features(image).vector()
        xs.append(vec)
        ys.append(row.label)
        paths.append(row.path)
    return np.stack(xs), np.asarray(ys, dtype=np.int64), paths


def _metrics(pred: np.ndarray, y: np.ndarray) -> tuple[float, float, int, int, int]:
    tp = int(((pred == 1) & (y == 1)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    recall = tp / max(tp + fn, 1)
    precision = tp / max(tp + fp, 1)
    return recall, precision, tp, fn, fp


def _search_thresholds(x: np.ndarray, y: np.ndarray) -> tuple[HeuristicThresholds, np.ndarray, float, float]:
    grid = []
    for t_el in (12.0, 18.0, 28.0, 40.0):
        for t_as in (4.0, 6.0, 9.0):
            for t_fill in (0.4, 0.55, 0.75):
                for t_ink in (0.002, 0.004, 0.008):
                    for t_bj in (0.01, 0.02, 0.04):
                        for t_edge in (0.80, 0.90, 0.97):
                            for t_curv in (0.12, 0.22, 0.35):
                                grid.append(
                                    HeuristicThresholds(
                                        t_elongation=t_el,
                                        t_aspect=t_as,
                                        t_bbox_fill_line=t_fill,
                                        t_ink_junk=t_ink,
                                        t_bbox_junk=t_bj,
                                        t_edge_hug=t_edge,
                                        t_curvature=t_curv,
                                    )
                                )
    best: HeuristicThresholds | None = None
    best_key = (-1.0, -1.0, 0)
    best_scores = _scores_heuristic(x, HeuristicGate())
    for thresholds in grid:
        scores = _scores_heuristic(x, HeuristicGate(thresholds))
        pred = (scores >= 0.5).astype(np.int64)
        recall, precision, _tp, fn, _fp = _metrics(pred, y)
        key = (1.0 if recall >= 0.98 else recall, precision, -fn)
        if key > best_key:
            best_key = key
            best = thresholds
            best_scores = scores
    chosen = best or HeuristicThresholds()
    pred = (best_scores >= 0.5).astype(np.int64)
    recall, precision, tp, fn, fp = _metrics(pred, y)
    if recall < 0.98:
        chosen = HeuristicThresholds(
            t_elongation=80.0,
            t_aspect=12.0,
            t_bbox_fill_line=0.9,
            t_ink_junk=0.001,
            t_bbox_junk=0.008,
            t_edge_hug=0.99,
            t_curvature=0.05,
        )
        best_scores = _scores_heuristic(x, HeuristicGate(chosen))
        pred = (best_scores >= 0.5).astype(np.int64)
        recall, precision, tp, fn, fp = _metrics(pred, y)
    print(
        f"train heuristic search recall={recall:.4f} precision={precision:.4f} "
        f"tp={tp} fn={fn} fp={fp}",
        flush=True,
    )
    return chosen, best_scores, recall, precision


def _scores_heuristic(matrix: np.ndarray, gate: HeuristicGate) -> np.ndarray:
    from chess_core.ocr.gate.features import RawFeatures

    out = []
    for row in matrix:
        feats = RawFeatures(*[float(v) for v in row])
        out.append(gate.p_content(feats))
    return np.asarray(out, dtype=np.float64)


def _fit_logit(x: np.ndarray, y: np.ndarray, *, pos_boost: float = 1.0) -> dict[str, list[float] | float]:
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    z = (x - mean) / std
    w = np.zeros(z.shape[1], dtype=np.float64)
    b = 0.0
    pos = max(float((y == 1).sum()), 1.0)
    neg = max(float((y == 0).sum()), 1.0)
    weights = np.where(y == 1, pos_boost * neg / pos, 1.0)
    lr = 0.08
    for _ in range(800):
        logits = z @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(logits, -20, 20)))
        err = (p - y) * weights
        w -= lr * (z.T @ err) / len(y)
        b -= lr * float(err.mean())
    return {
        "weights": w.tolist(),
        "bias": float(b),
        "mean": mean.tolist(),
        "std": std.tolist(),
        "features": list(FEATURE_NAMES),
        "n_parameters": int(len(w) + 1),
        "n_features": int(len(w)),
    }


def _logit_scores(matrix: np.ndarray, payload: dict) -> np.ndarray:
    w = np.asarray(payload["weights"])
    mean = np.asarray(payload["mean"])
    std = np.asarray(payload["std"])
    z = (matrix - mean) / np.maximum(std, 1e-6)
    logits = z @ w + float(payload["bias"])
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -20, 20)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Подобрать пороги content-gate на train.")
    parser.parse_args(argv)
    rows = load_catalog()
    if not rows:
        raise SystemExit("нет data/gate/labels.json — сначала collect_gate_crops")
    assert_sheet_disjoint(rows)
    train = train_rows(rows)
    hold = holdout_rows(rows)
    x_train, y_train, train_paths = _xy(train)
    (gate_root() / "fit_paths.json").write_text(
        json.dumps({"train_paths": train_paths}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert_holdout_unused_by_fit(train_paths, rows)
    thresholds, scores, recall, precision = _search_thresholds(x_train, y_train)
    save_thresholds(thresholds_path(), thresholds)
    model_payload = None
    used = "heuristic"
    if precision < 0.90 and recall >= 0.98:
        print("B3: heuristic precision < 0.90 при recall>=0.98 — логит на 7 фичах + 8x8")
        x_full, _, _ = _xy(train, with_tile=True)
        model_payload = _fit_logit(x_full, y_train)
        if int(model_payload["n_parameters"]) > 5000:
            raise RuntimeError("gate model too large")
        model_scores = _logit_scores(x_full, model_payload)
        h_scores = _scores_heuristic(x_train, HeuristicGate(thresholds))
        scores = np.maximum(h_scores, model_scores)
        pred = (scores >= 0.5).astype(np.int64)
        recall, precision, tp, fn, fp = _metrics(pred, y_train)
        if recall < 0.98:
            model_payload = _fit_logit(x_full, y_train, pos_boost=8.0)
            model_scores = _logit_scores(x_full, model_payload)
            scores = np.maximum(h_scores, model_scores)
            pred = (scores >= 0.5).astype(np.int64)
            recall, precision, tp, fn, fp = _metrics(pred, y_train)
        print(f"train ensemble recall={recall:.4f} precision={precision:.4f} tp={tp} fn={fn} fp={fp}")
        used = "model"
        model_path().write_text(json.dumps(model_payload, indent=2), encoding="utf-8")
    elif model_path().is_file():
        model_path().unlink()
    a, b = platt_fit(scores, y_train)
    cal = platt_apply(scores, a, b)
    pos_mask = y_train == 1
    neg_mask = y_train == 0
    pos_cal = cal[pos_mask]
    neg_cal = cal[neg_mask]
    apply_platt = bool(
        pos_cal.size
        and neg_cal.size
        and float(pos_cal.min()) >= 0.5
        and float(neg_cal.min()) < 0.5
        and float(pos_cal.mean() - neg_cal.mean()) >= 0.15
        and float(np.std(cal)) >= 0.08
    )
    x_hold, y_hold, hold_paths = _xy(hold, with_tile=(used == "model"))
    del hold_paths
    if used == "model" and model_payload is not None:
        hold_model = _logit_scores(x_hold, model_payload)
        hold_h = _scores_heuristic(x_hold[:, : len(FEATURE_NAMES)], HeuristicGate(thresholds))
        hold_scores = np.maximum(hold_h, hold_model)
    else:
        hold_scores = _scores_heuristic(x_hold[:, : len(FEATURE_NAMES)], HeuristicGate(thresholds))
    hold_cal = platt_apply(hold_scores, a, b) if apply_platt else hold_scores
    points = binary_pr(hold_cal, y_hold)
    chosen = operating_point(points, min_recall=0.98)
    auc = pr_auc(points)
    deployed = 0.5
    pred_h = (hold_cal >= deployed).astype(np.int64)
    eaten = int(((pred_h == 0) & (y_hold == 1)).sum())
    hold_recall, hold_prec, *_rest = _metrics(pred_h, y_hold)
    report = {
        "used": used,
        "train_recall": recall,
        "train_precision": precision,
        "holdout": {
            "pr_auc": auc,
            "ece": ece_score(hold_cal, y_hold),
            "precision": hold_prec,
            "recall": hold_recall,
            "deployed_threshold": deployed,
            "positives_eaten": eaten,
            "n_pos": int((y_hold == 1).sum()),
            "n_neg": int((y_hold == 0).sum()),
            "operating_point": None
            if chosen is None
            else {
                "threshold": chosen.threshold,
                "precision": chosen.precision,
                "recall": chosen.recall,
                "tp": chosen.tp,
                "fp": chosen.fp,
                "fn": chosen.fn,
            },
        },
        "platt": {"a": a, "b": b, "apply": apply_platt},
        "thresholds": thresholds.to_dict(),
        "model": used == "model",
    }
    (gate_root() / "calibration.json").write_text(
        json.dumps({"a": a, "b": b, "apply": apply_platt}, indent=2),
        encoding="utf-8",
    )
    reliability_png(hold_cal, y_hold, gate_root() / "reliability.png")
    pr_curve_png(points, chosen, gate_root() / "pr_curve.png")
    (gate_root() / "holdout_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report["holdout"], ensure_ascii=False, indent=2))
    print(f"positives eaten on holdout={eaten}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
