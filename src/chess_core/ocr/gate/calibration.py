"""Gate-only calibration (not the CNN). Platt on train, ECE/PR on holdout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class PrPoint:
    threshold: float
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int


def binary_pr(scores: np.ndarray, labels: np.ndarray) -> list[PrPoint]:
    order = np.argsort(-scores)
    y = labels[order]
    points: list[PrPoint] = []
    tp = fp = 0
    n_pos = int(y.sum())
    for i, score in enumerate(scores[order]):
        if y[i] == 1:
            tp += 1
        else:
            fp += 1
        fn = n_pos - tp
        prec = tp / max(tp + fp, 1)
        rec = tp / max(n_pos, 1)
        points.append(PrPoint(float(score), float(prec), float(rec), tp, fp, fn))
    return points


def pr_auc(points: Sequence[PrPoint]) -> float:
    if len(points) < 2:
        return 0.0
    rec = np.array([item.recall for item in points])
    prec = np.array([item.precision for item in points])
    return float(np.trapezoid(prec, rec)) if hasattr(np, "trapezoid") else float(np.trapz(prec, rec))


def operating_point(points: Sequence[PrPoint], *, min_recall: float) -> PrPoint | None:
    ok = [item for item in points if item.recall >= min_recall]
    if not ok:
        return None
    return max(ok, key=lambda item: (item.precision, item.recall))


def ece_score(scores: np.ndarray, labels: np.ndarray, *, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = max(len(labels), 1)
    ece = 0.0
    for i in range(bins):
        mask = (scores >= edges[i]) & (scores < edges[i + 1] if i < bins - 1 else scores <= edges[i + 1])
        if not np.any(mask):
            continue
        acc = float(labels[mask].mean())
        conf = float(scores[mask].mean())
        ece += (float(mask.mean())) * abs(acc - conf)
    del total
    return float(ece)


def platt_fit(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    """Two-parameter logistic on raw scores. Returns (a, b) for 1/(1+exp(a*s+b))."""

    s = scores.astype(np.float64)
    y = labels.astype(np.float64)
    a, b = -1.0, 0.0
    lr = 0.05
    for _ in range(400):
        z = np.clip(a * s + b, -20, 20)
        p = 1.0 / (1.0 + np.exp(z))
        err = p - y
        a -= lr * float((err * s).mean())
        b -= lr * float(err.mean())
    return float(a), float(b)


def platt_apply(scores: np.ndarray, a: float, b: float) -> np.ndarray:
    z = np.clip(a * scores + b, -20, 20)
    return 1.0 / (1.0 + np.exp(z))


def pr_curve_png(points: Sequence[PrPoint], chosen: PrPoint | None, path: Path) -> None:
    import cv2

    canvas = np.full((280, 280, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (40, 40), (240, 240), (30, 30, 30), 1)
    pts = []
    for item in points:
        px = int(40 + 200 * item.recall)
        py = int(240 - 200 * item.precision)
        pts.append((px, py))
    if len(pts) >= 2:
        cv2.polylines(canvas, [np.array(pts, dtype=np.int32)], False, (40, 80, 200), 1)
    if chosen is not None:
        px = int(40 + 200 * chosen.recall)
        py = int(240 - 200 * chosen.precision)
        cv2.circle(canvas, (px, py), 5, (20, 140, 40), -1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", canvas)[1].tofile(str(path))


def reliability_png(scores: np.ndarray, labels: np.ndarray, path: Path, *, bins: int = 10) -> None:
    import cv2

    edges = np.linspace(0.0, 1.0, bins + 1)
    xs, ys = [], []
    for i in range(bins):
        mask = (scores >= edges[i]) & (scores < edges[i + 1] if i < bins - 1 else scores <= edges[i + 1])
        if not np.any(mask):
            continue
        xs.append(float(scores[mask].mean()))
        ys.append(float(labels[mask].mean()))
    canvas = np.full((280, 280, 3), 255, dtype=np.uint8)
    cv2.line(canvas, (40, 240), (240, 40), (180, 180, 180), 1)
    cv2.rectangle(canvas, (40, 40), (240, 240), (30, 30, 30), 1)
    pts = []
    for x, y in zip(xs, ys):
        px = int(40 + 200 * x)
        py = int(240 - 200 * y)
        pts.append((px, py))
        cv2.circle(canvas, (px, py), 4, (40, 80, 200), -1)
    if len(pts) >= 2:
        cv2.polylines(canvas, [np.array(pts, dtype=np.int32)], False, (40, 80, 200), 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".png", canvas)[1].tofile(str(path))
