"""Blind contact sheets: image and anonymous id only. No role, no prediction."""

from __future__ import annotations

import math
import re

import numpy as np

_BLIND_ID = re.compile(r"^[gc][0-9]{3}$")


def shuffled_indices(n: int, seed: int) -> list[int]:
    rng = np.random.default_rng(seed)
    order = np.arange(n)
    rng.shuffle(order)
    return [int(i) for i in order.tolist()]


def rankdata(values: list[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr), dtype=np.float64)
    ranks[order] = np.arange(1, len(arr) + 1, dtype=np.float64)
    start = 0
    while start < len(arr):
        end = start + 1
        while end < len(arr) and arr[order[end]] == arr[order[start]]:
            end += 1
        if end - start > 1:
            avg = float(ranks[order[start:end]].mean())
            ranks[order[start:end]] = avg
        start = end
    return ranks


def spearman(left: list[float] | np.ndarray, right: list[float] | np.ndarray) -> float:
    a = rankdata(left)
    b = rankdata(right)
    a = a - float(a.mean())
    b = b - float(b.mean())
    denom = math.sqrt(float(np.sum(a * a)) * float(np.sum(b * b)))
    if denom == 0.0:
        return float("nan")
    return float(np.sum(a * b) / denom)


def render_blind_sheet(
    images: list[np.ndarray],
    ids: list[str],
    *,
    cols: int = 4,
    gap: int = 12,
) -> tuple[np.ndarray, list[str]]:
    """Draw crops and ids. Returns the canvas and the exact strings painted on it."""

    import cv2

    if len(images) != len(ids):
        raise ValueError("images and ids must be aligned")
    if cols < 1:
        raise ValueError("cols must be positive")
    captions: list[str] = []
    for item in ids:
        text = str(item)
        if _BLIND_ID.fullmatch(text) is None:
            raise ValueError(f"blind id must look like g001 or c001, got {text!r}")
        captions.append(text)
    if not images:
        return np.full((8, 8), 255, dtype=np.uint8), captions

    widths = [int(np.asarray(image).shape[1]) for image in images]
    heights = [int(np.asarray(image).shape[0]) for image in images]
    caption_h = 28
    n_rows = math.ceil(len(images) / cols)
    col_w = [
        max(widths[col::cols]) if widths[col::cols] else 1 for col in range(cols)
    ]
    row_h = []
    for row in range(n_rows):
        chunk = heights[row * cols : (row + 1) * cols]
        row_h.append(max(chunk) if chunk else 1)
    width = gap + sum(col_w[c] + gap for c in range(cols))
    height = gap + sum(row_h[r] + caption_h + gap for r in range(n_rows))
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    y = gap
    for row in range(n_rows):
        x = gap
        for col in range(cols):
            index = row * cols + col
            if index >= len(images):
                break
            gray = np.asarray(images[index])
            if gray.ndim == 3:
                gray = gray[..., 0]
            tile = cv2.cvtColor(np.ascontiguousarray(gray), cv2.COLOR_GRAY2BGR)
            h, w = tile.shape[:2]
            canvas[y : y + h, x : x + w] = tile
            cv2.putText(
                canvas,
                captions[index],
                (x, y + h + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )
            x += col_w[col] + gap
        y += row_h[row] + caption_h + gap
    return canvas, captions
