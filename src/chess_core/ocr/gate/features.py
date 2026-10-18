"""Raw-crop features for the content gate. Do not compute these on mnist_pad tiles."""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


FEATURE_NAMES: tuple[str, ...] = (
    "ink_ratio",
    "bbox_fill",
    "aspect",
    "stroke_width",
    "elongation",
    "edge_hug",
    "curvature_proxy",
)


@dataclass(frozen=True, slots=True)
class RawFeatures:
    ink_ratio: float
    bbox_fill: float
    aspect: float
    stroke_width: float
    elongation: float
    edge_hug: float
    curvature_proxy: float

    def vector(self) -> np.ndarray:
        return np.array([getattr(self, name) for name in FEATURE_NAMES], dtype=np.float64)

    def to_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


def _to_gray(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 3:
        import cv2

        return cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    return array


def otsu_ink(gray: np.ndarray) -> np.ndarray:
    import cv2

    if gray.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _thr, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return (binary > 0).astype(np.uint8)


def extract_raw_features(image: np.ndarray) -> RawFeatures:
    """Seven features from a raw gray/BGR crop, before mnist_pad."""

    import cv2

    gray = _to_gray(image)
    height, width = gray.shape[:2]
    area = max(height * width, 1)
    ink = otsu_ink(gray)
    n_ink = int(np.sum(ink, dtype=np.int64))
    ink_ratio = n_ink / area
    if n_ink == 0:
        return RawFeatures(0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0)
    ys, xs = np.where(ink > 0)
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    bw = max(x2 - x1, 1)
    bh = max(y2 - y1, 1)
    bbox_fill = (bh * bw) / area
    aspect = bw / bh
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    on_ink = dist[ink > 0]
    stroke_width = float(np.median(on_ink) * 2.0) if on_ink.size else 0.0
    coords = np.column_stack((xs.astype(np.float64), ys.astype(np.float64)))
    centered = coords - coords.mean(axis=0)
    cov = np.cov(centered, rowvar=False)
    if np.ndim(cov) == 0:
        elongation = 1.0
    else:
        cov = np.atleast_2d(cov)
        eig = np.linalg.eigvalsh(cov)
        eig = np.sort(np.maximum(eig, 1e-6))
        elongation = float(eig[-1] / eig[0])
    border = np.zeros_like(ink)
    pad = max(1, min(2, height // 8, width // 8))
    border[:pad, :] = 1
    border[-pad:, :] = 1
    border[:, :pad] = 1
    border[:, -pad:] = 1
    edge_hug = float(np.sum(ink * border, dtype=np.int64) / n_ink)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    angles = np.arctan2(gy[ink > 0], gx[ink > 0])
    curvature = float(np.var(angles)) if angles.size > 4 else 0.0
    return RawFeatures(
        ink_ratio=float(ink_ratio),
        bbox_fill=float(bbox_fill),
        aspect=float(aspect),
        stroke_width=float(stroke_width),
        elongation=float(elongation),
        edge_hug=float(edge_hug),
        curvature_proxy=float(curvature),
    )


def downsample_8x8(image: np.ndarray) -> np.ndarray:
    """8x8 raw gray, flattened to [0, 1]. Used only by the tiny B3 logit."""

    import cv2

    gray = _to_gray(image)
    if gray.size == 0:
        return np.zeros(64, dtype=np.float64)
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    return (small.astype(np.float64) / 255.0).ravel()


def gate_vector(image: np.ndarray) -> np.ndarray:
    feats = extract_raw_features(image)
    return np.concatenate([feats.vector(), downsample_8x8(image)])


def is_hard_positive(features: RawFeatures) -> bool:
    """Thin 1 / x / small р / edge-hugging ink — naive gates drop these."""

    thin = features.aspect > 2.4 or features.aspect < 0.35
    faint = features.ink_ratio < 0.07 and features.bbox_fill > 0.02
    skinny = features.stroke_width < 1.35
    on_edge = features.edge_hug > 0.42
    return bool(thin or faint or skinny or on_edge)
