"""Distribution helpers for the P5.0b diagnostic. No training, no model."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from chess_core.ocr.gate.features import otsu_ink


def wilson_interval(hits: int, n: int, *, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion. Empty n returns NaN."""

    if n <= 0:
        return float("nan"), float("nan")
    p = hits / n
    z2 = z * z
    den = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / den
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / den
    return centre - margin, centre + margin


def proportion(hits: int, n: int) -> dict[str, float | int]:
    lo, hi = wilson_interval(hits, n)
    return {
        "hits": int(hits),
        "n": int(n),
        "p": (hits / n) if n else float("nan"),
        "ci95_lo": lo,
        "ci95_hi": hi,
    }


def quantiles(values: Sequence[float]) -> dict[str, float]:
    arr = np.asarray(list(values), dtype=np.float64)
    if arr.size == 0:
        nan = float("nan")
        return {"min": nan, "p10": nan, "median": nan, "p90": nan, "max": nan, "n": 0}
    return {
        "min": float(np.min(arr)),
        "p10": float(np.quantile(arr, 0.10)),
        "median": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.90)),
        "max": float(np.max(arr)),
        "n": int(arr.size),
    }


def stroke_width_px(gray: np.ndarray) -> float:
    """2 * median distance-transform radius of the Otsu ink mask."""

    import cv2

    ink = otsu_ink(gray)
    n_ink = int(np.sum(ink, dtype=np.int64))
    if n_ink == 0:
        return 0.0
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    return float(np.median(dist[ink > 0]) * 2.0)


def crop_features(source: np.ndarray, normalized: np.ndarray) -> dict[str, float]:
    """Features in photo pixels and after mnist_pad. ``source`` is the raw crop."""

    gray = np.asarray(source)
    if gray.ndim == 3:
        gray = gray[..., 0]
    norm = np.asarray(normalized)
    if norm.ndim == 3:
        norm = norm[..., 0]
    height, width = gray.shape[:2]
    ink = otsu_ink(gray)
    n_ink = int(np.sum(ink, dtype=np.int64))
    area = max(height * width, 1)
    if n_ink == 0:
        bbox_fill = 0.0
        aspect = 1.0
        edge = 0.0
        contrast = 0.0
        ink_w = 1.0
    else:
        ys, xs = np.where(ink > 0)
        bw = max(int(xs.max()) - int(xs.min()) + 1, 1)
        bh = max(int(ys.max()) - int(ys.min()) + 1, 1)
        bbox_fill = (bw * bh) / area
        aspect = bw / bh
        border = np.zeros_like(ink)
        pad = max(1, min(2, height // 8, width // 8))
        border[:pad, :] = 1
        border[-pad:, :] = 1
        border[:, :pad] = 1
        border[:, -pad:] = 1
        edge = float(np.sum(ink * border, dtype=np.int64) / n_ink)
        ink_vals = gray[ink > 0].astype(np.float64)
        contrast = float(np.quantile(ink_vals, 0.95) - np.quantile(ink_vals, 0.05))
        ink_w = float(bw)
    norm_ink = otsu_ink(norm)
    if int(np.sum(norm_ink, dtype=np.int64)) == 0:
        w_norm = 1.0
    else:
        xs = np.where(norm_ink > 0)[1]
        w_norm = float(max(int(xs.max()) - int(xs.min()) + 1, 1))
    return {
        "w_src": float(width),
        "h_src": float(height),
        "stroke_src": stroke_width_px(gray),
        "stroke_norm": stroke_width_px(norm),
        "ink_ratio": n_ink / area,
        "bbox_fill": float(bbox_fill),
        "aspect": float(aspect),
        "edge_touch": float(edge),
        "contrast": float(contrast),
        "eff_scale": float(width) / w_norm,
        "ink_w_src": float(ink_w),
        "w_norm": float(w_norm),
    }


FEATURE_NAMES: tuple[str, ...] = (
    "w_src",
    "h_src",
    "stroke_src",
    "stroke_norm",
    "ink_ratio",
    "bbox_fill",
    "aspect",
    "edge_touch",
    "contrast",
    "eff_scale",
)
