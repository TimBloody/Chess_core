"""How a raw glyph crop becomes the 28x28 tensor the CNN sees.

Training and inference must call the same prep. Ablations are objects,
selected by name from p5_pipeline.json, not by branching inside MSER.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from chess_core.infra.paths import project_root


@dataclass(frozen=True, slots=True)
class PrepConfig:
    name: str = "baseline"
    invert: bool = False
    transpose: bool = False
    margin: int = 0
    box: int = 20
    binarize: str = "none"  # none | otsu | adaptive
    normalize: str = "div255"  # div255 | emnist_z

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "invert": self.invert,
            "transpose": self.transpose,
            "margin": self.margin,
            "box": self.box,
            "binarize": self.binarize,
            "normalize": self.normalize,
        }


def pipeline_path() -> Path:
    return project_root() / "output" / "ocr_runs" / "p5_pipeline.json"


def load_prep_config(path: Path | None = None) -> PrepConfig:
    target = path or pipeline_path()
    if not target.is_file():
        return PrepConfig()
    payload = json.loads(target.read_text(encoding="utf-8"))
    selected = payload.get("selected") or payload
    return PrepConfig(
        name=str(selected.get("name") or "baseline"),
        invert=bool(selected.get("invert")),
        transpose=bool(selected.get("transpose")),
        margin=int(selected.get("margin") or 0),
        box=int(selected.get("box") or 20),
        binarize=str(selected.get("binarize") or "none"),
        normalize=str(selected.get("normalize") or "div255"),
    )


def prepare_crop(crop: np.ndarray, config: PrepConfig | None = None) -> np.ndarray:
    """Raw gray crop -> 28x28 dark-ink canvas. Does not divide by 255."""

    cfg = config or PrepConfig()
    gray = np.asarray(crop)
    if gray.ndim == 3:
        import cv2

        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    gray = np.ascontiguousarray(gray)
    if gray.size == 0:
        return np.full((28, 28), 255, dtype=np.uint8)
    if cfg.transpose:
        gray = np.ascontiguousarray(gray.T)
    if cfg.invert:
        gray = np.ascontiguousarray(255 - gray)
    if cfg.binarize == "otsu":
        gray = _otsu(gray)
    elif cfg.binarize == "adaptive":
        gray = _adaptive(gray)
    elif cfg.binarize != "none":
        raise ValueError(f"unknown binarize mode {cfg.binarize!r}")
    if cfg.margin > 0:
        return _mnist_pad_with_margin(gray, box=int(cfg.box), margin=int(cfg.margin))
    return _mnist_pad(gray, box=int(cfg.box))


def _mnist_pad(patch: np.ndarray, *, size: int = 28, box: int = 20) -> np.ndarray:
    """Same placement as ``ocr_mser.mnist_pad``: tight crop, fit in ``box``, mass-center."""

    import cv2

    canvas = np.full((size, size), 255, dtype=np.uint8)
    gray = np.asarray(patch)
    if gray.size == 0:
        return canvas
    ink = gray < 175
    if not np.any(ink):
        return canvas
    ys, xs = np.where(ink)
    tight = gray[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    height, width = tight.shape
    scale = box / max(height, width, 1)
    new_w = max(1, min(box, int(round(width * scale))))
    new_h = max(1, min(box, int(round(height * scale))))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    scaled = cv2.resize(tight, (new_w, new_h), interpolation=interpolation)
    weight = np.clip(255.0 - scaled.astype(np.float32), 0.0, 255.0)
    total = float(np.sum(weight))
    if total <= 0.0:
        return canvas
    gy, gx = np.indices(scaled.shape)
    cy = float(np.sum(gy * weight) / total)
    cx = float(np.sum(gx * weight) / total)
    center = (size - 1) / 2.0
    y0 = int(np.clip(round(center - cy), 0, size - new_h))
    x0 = int(np.clip(round(center - cx), 0, size - new_w))
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = scaled
    return canvas


def _mnist_pad_with_margin(gray: np.ndarray, *, box: int, margin: int) -> np.ndarray:
    """White ring after the tight crop, so the stroke is not scaled to the box edge.

    ``mnist_pad`` tight-crops ink and would delete a white ring added before it.
    """

    canvas = np.full((28, 28), 255, dtype=np.uint8)
    ink = gray < 175
    if not np.any(ink):
        return canvas
    ys, xs = np.where(ink)
    tight = gray[int(ys.min()) : int(ys.max()) + 1, int(xs.min()) : int(xs.max()) + 1]
    tight = np.pad(tight, margin, mode="constant", constant_values=255)
    import cv2

    height, width = tight.shape
    scale = box / max(height, width, 1)
    new_w = max(1, min(box, int(round(width * scale))))
    new_h = max(1, min(box, int(round(height * scale))))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    scaled = cv2.resize(tight, (new_w, new_h), interpolation=interpolation)
    y0 = max(0, (28 - new_h) // 2)
    x0 = max(0, (28 - new_w) // 2)
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = scaled
    return canvas


def _otsu(gray: np.ndarray) -> np.ndarray:
    import cv2

    _thr, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _adaptive(gray: np.ndarray) -> np.ndarray:
    import cv2

    if min(gray.shape[:2]) < 3:
        return _otsu(gray)
    block = max(3, (min(gray.shape[:2]) // 2) * 2 + 1)
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        2,
    )


ABLATIONS: tuple[PrepConfig, ...] = (
    PrepConfig(name="baseline"),
    PrepConfig(name="D1_invert", invert=True),
    PrepConfig(name="D2_transpose", transpose=True),
    PrepConfig(name="D4_margin3", margin=3),
    PrepConfig(name="D4_margin4", margin=4),
    PrepConfig(name="D5_otsu", binarize="otsu"),
    PrepConfig(name="D5_adaptive", binarize="adaptive"),
    PrepConfig(name="D7_box16", box=16),
    PrepConfig(name="D7_box20", box=20),
    PrepConfig(name="D7_box24", box=24),
    PrepConfig(name="D2_transpose_box20", transpose=True, box=20),
)
