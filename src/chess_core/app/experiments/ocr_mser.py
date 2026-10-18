"""Split a move cell into MNIST-style glyphs. Not whole-cell OCR.

Whole-cell nets almost never tell e4 from g4. Character-level can tell e from g,
but only after a clean split: Nf3 → N, f, 3 even when the strokes touch.

Pipeline:
  1. Wipe printed grid rules, tight-crop writing (drop empty margins).
  2. MSER on CLAHE gray; keep nested *leaf* regions of glyph-like size
     (about 11–52% of the trimmed writing width).
  3. Vertical blocks from hole-filled ink — true gaps, not the hole in e/8/4.
  4. Over-wide / under-counted blocks are cut at a thin neck (projection +
     stroke thickness + drop-fall), snapped to nearby MSER edges.
  5. Tight-crop each glyph onto a MNIST canvas: 28×28, ink fitted in a 20×20
     box, missing white margin drawn in, center of mass at the canvas center.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

# LeCun: fit the mark in a 20×20 box, then center it on a 28×28 field.
_MNIST_SIZE = 28
_MNIST_BOX = 20
_WORK_HEIGHT = 96
_MIN_GLYPHS = 1
_MAX_GLYPHS = 5
# A finished chess glyph is typically 18–48% of the trimmed writing width.
_MIN_WIDTH_FRAC = 0.11
_MAX_WIDTH_FRAC = 0.52
# Width / (k * height) ≈ glyph count when letters are glued together.
_GLYPH_ASPECT = 0.70
# A single letter is about as wide as it is tall; more than this is several glyphs.
_WIDE_ASPECT = 1.22


@dataclass(frozen=True, slots=True)
class GlyphBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)


@dataclass(frozen=True, slots=True)
class Glyph:
    box: GlyphBox
    mnist: np.ndarray


@dataclass(frozen=True, slots=True)
class CellGlyphs:
    content: GlyphBox | None
    expected: int
    glyphs: tuple[Glyph, ...]


def to_gray(image: Any) -> np.ndarray:
    from pathlib import Path

    if isinstance(image, (str, Path)):
        encoded = np.fromfile(str(image), dtype=np.uint8)
        loaded = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        if loaded is None:
            raise FileNotFoundError(image)
        return loaded
    array = np.asarray(image)
    if array.ndim == 2:
        return array
    return cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)


def wipe_grid_rules(gray: np.ndarray) -> np.ndarray:
    """Whiten long printed table rules so they are not treated as letters."""

    cleaned = gray.copy()
    dark = cleaned < 190
    height, width = cleaned.shape
    for x in np.where(np.sum(dark, axis=0) >= max(4, round(height * 0.65)))[0]:
        cleaned[:, max(0, int(x) - 1) : min(width, int(x) + 2)] = 255
    for y in range(height):
        frac = 0.48 if y < 3 or y >= height - 3 else 0.70
        if int(np.sum(dark[y])) >= max(4, round(width * frac)):
            cleaned[max(0, y - 1) : min(height, y + 2), :] = 255
    return cleaned


def ink_mass(image: Any) -> int:
    binary = _ink_binary(to_gray(image))
    height, width = binary.shape
    if height < 8 or width < 8:
        return 0
    return int(np.count_nonzero(binary[2 : height - 2, 2 : width - 2]))


def glyph_boxes(image: Any) -> list[GlyphBox]:
    return [item.box for item in segment_cell(image).glyphs]


def segment_cell(image: Any) -> CellGlyphs:
    gray = wipe_grid_rules(to_gray(image))
    binary = _ink_binary(gray)
    content = _content_bbox(binary)
    if content is None:
        return CellGlyphs(content=None, expected=0, glyphs=())
    crop_g = gray[content.y1 : content.y2, content.x1 : content.x2]
    crop_b = binary[content.y1 : content.y2, content.x1 : content.x2]
    work_g, work_b, scale = _working_image(crop_g, crop_b)
    filled = _fill_holes(work_b)
    mser = _mser_leaves(_mser_boxes(_clahe(work_g)), work_g.shape[1], work_g.shape[0])
    blocks = _merge_close_blocks(_vertical_blocks(filled), filled.shape[0])
    expected = _expected_glyph_count(filled, blocks)
    work_boxes = _choose_boxes(work_b, filled, mser, blocks, expected)
    work_boxes = _drop_tiny(work_boxes, GlyphBox(0, 0, work_b.shape[1], work_b.shape[0]))
    work_boxes = _merge_box_fragments(work_boxes, work_b.shape[1], work_b.shape[0])
    boxes = [
        _map_box(box, scale, content.x1, content.y1, gray.shape[1], gray.shape[0])
        for box in work_boxes
    ]
    boxes = [box for box in boxes if box.width >= 2 and box.height >= 2]
    glyphs = tuple(
        Glyph(box=box, mnist=mnist_pad(gray[box.y1 : box.y2, box.x1 : box.x2]))
        for box in boxes
    )
    return CellGlyphs(content=content, expected=expected, glyphs=glyphs)


def mnist_pad(patch: np.ndarray, *, size: int = _MNIST_SIZE, box: int = _MNIST_BOX) -> np.ndarray:
    """Place one glyph on a white MNIST canvas.

    The ink is tight-cropped, scaled so its longer side is ``box`` pixels
    (aspect kept, edges stay gray), then shifted so its center of mass sits
    on the center of the ``size`` canvas. A tight crop with no paper around
    the stroke still gets a drawn white margin.
    """

    canvas = np.full((size, size), 255, dtype=np.uint8)
    gray = to_gray(patch)
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
    total = float(weight.sum())
    if total <= 0.0:
        return canvas
    gy, gx = np.indices(scaled.shape)
    cy = float((gy * weight).sum() / total)
    cx = float((gx * weight).sum() / total)
    center = (size - 1) / 2.0
    y0 = int(np.clip(round(center - cy), 0, size - new_h))
    x0 = int(np.clip(round(center - cx), 0, size - new_w))
    canvas[y0 : y0 + new_h, x0 : x0 + new_w] = scaled
    return canvas


def draw_glyph_overlay(image: Any, glyphs: CellGlyphs | None = None) -> np.ndarray:
    array = np.asarray(image)
    canvas = cv2.cvtColor(array, cv2.COLOR_GRAY2BGR) if array.ndim == 2 else array.copy()
    split = glyphs if glyphs is not None else segment_cell(canvas)
    if split.content is not None:
        box = split.content
        cv2.rectangle(canvas, (box.x1, box.y1), (box.x2, box.y2), (220, 160, 40), 1)
    for index, glyph in enumerate(split.glyphs):
        box = glyph.box
        cv2.rectangle(canvas, (box.x1, box.y1), (box.x2, box.y2), (40, 200, 70), 1)
        cv2.putText(
            canvas,
            str(index),
            (box.x1 + 1, max(box.y1 + 10, 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (40, 180, 255),
            1,
            cv2.LINE_AA,
        )
    return canvas


def glyph_montage(crops: list[Any], *, max_cells: int = 12) -> np.ndarray | None:
    if not crops:
        return None
    overlays = [draw_glyph_overlay(crop) for crop in crops[:max_cells]]
    return _tile(overlays, cols=min(6, len(overlays)))


def mnist_montage(crops: list[Any], *, max_cells: int = 12) -> np.ndarray | None:
    tiles: list[np.ndarray] = []
    for crop in crops[:max_cells]:
        for glyph in segment_cell(crop).glyphs:
            tiles.append(cv2.cvtColor(glyph.mnist, cv2.COLOR_GRAY2BGR))
    if not tiles:
        return None
    tiled = _tile(tiles, cols=min(8, len(tiles)))
    return cv2.resize(tiled, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)


def _ink_binary(gray: np.ndarray) -> np.ndarray:
    wiped = wipe_grid_rules(gray)
    if wiped.size == 0:
        return np.zeros_like(wiped)
    threshold, binary = cv2.threshold(wiped, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if threshold > 245:
        binary = np.where(wiped < 175, 255, 0).astype(np.uint8)
    return binary


def _clahe(gray: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(gray)


def _working_image(gray: np.ndarray, binary: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    height, width = gray.shape
    if height >= _WORK_HEIGHT:
        return gray, binary, 1.0
    scale = _WORK_HEIGHT / max(height, 1)
    size = (max(8, int(round(width * scale))), _WORK_HEIGHT)
    return (
        cv2.resize(gray, size, interpolation=cv2.INTER_CUBIC),
        cv2.resize(binary, size, interpolation=cv2.INTER_NEAREST),
        scale,
    )


def _map_box(box: GlyphBox, scale: float, origin_x: int, origin_y: int, width: int, height: int) -> GlyphBox:
    return GlyphBox(
        max(0, origin_x + int(round(box.x1 / scale))),
        max(0, origin_y + int(round(box.y1 / scale))),
        min(width, origin_x + int(round(box.x2 / scale))),
        min(height, origin_y + int(round(box.y2 / scale))),
    )


def _content_bbox(binary: np.ndarray) -> GlyphBox | None:
    cleaned = _drop_specks(binary)
    ys, xs = np.where(cleaned > 0)
    if len(xs) < 8:
        return None
    height, width = binary.shape
    pad_x = max(1, round(width * 0.02))
    pad_y = max(1, round(height * 0.03))
    return GlyphBox(
        max(0, int(xs.min()) - pad_x),
        max(0, int(ys.min()) - pad_y),
        min(width, int(xs.max()) + pad_x + 1),
        min(height, int(ys.max()) + pad_y + 1),
    )


def _drop_specks(binary: np.ndarray) -> np.ndarray:
    height, width = binary.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    keep = np.zeros_like(binary)
    min_area = max(8, round(height * width * 0.0015))
    min_h = max(5, round(height * 0.12))
    for index in range(1, count):
        _x, _y, w, h, area = (int(v) for v in stats[index])
        if area < min_area and h < min_h:
            continue
        if h <= 2 and w > width * 0.5:
            continue
        keep[labels == index] = 255
    return keep


def _fill_holes(binary: np.ndarray) -> np.ndarray:
    """Close interiors of e/8/4/A so projection valleys are real gaps, not holes."""

    if binary.size == 0:
        return binary
    inverse = cv2.bitwise_not(binary)
    height, width = inverse.shape
    seed = None
    for x in range(width):
        if inverse[0, x]:
            seed = (x, 0)
            break
        if inverse[height - 1, x]:
            seed = (x, height - 1)
            break
    if seed is None:
        for y in range(height):
            if inverse[y, 0]:
                seed = (0, y)
                break
            if inverse[y, width - 1]:
                seed = (width - 1, y)
                break
    if seed is None:
        return binary
    flood = inverse.copy()
    cv2.floodFill(flood, np.zeros((height + 2, width + 2), np.uint8), seed, 0)
    filled = binary.copy()
    filled[(flood == 255) & (binary == 0)] = 255
    return filled


def _mser_boxes(gray: np.ndarray) -> list[GlyphBox]:
    height, width = gray.shape
    if height < 8 or width < 8:
        return []
    mser = cv2.MSER_create()
    mser.setDelta(4)
    mser.setMinArea(max(12, int(height * width * 0.004)))
    mser.setMaxArea(max(40, int(height * width * 0.72)))
    mser.setMaxVariation(0.35)
    mser.setMinDiversity(0.12)
    regions, _ = mser.detectRegions(gray)
    found: list[GlyphBox] = []
    for region in regions:
        points = np.asarray(region)
        if points.ndim == 1:
            points = points.reshape(-1, 2)
        if len(points) < 8:
            continue
        found.append(
            GlyphBox(
                int(points[:, 0].min()),
                int(points[:, 1].min()),
                int(points[:, 0].max()) + 1,
                int(points[:, 1].max()) + 1,
            )
        )
    return found


def _mser_leaves(boxes: list[GlyphBox], width: int, height: int) -> list[GlyphBox]:
    """Drop parent blobs that contain two or more glyph-sized children."""

    min_h = max(6, round(height * 0.34))
    min_w = max(3, round(width * _MIN_WIDTH_FRAC * 0.55))
    max_w = max(min_w + 1, round(width * _MAX_WIDTH_FRAC))
    sized = [box for box in _unique_boxes(boxes) if box.height >= min_h and box.width >= min_w]
    glyph_like = [box for box in sized if box.width <= max_w]
    keep: list[GlyphBox] = []
    for box in glyph_like:
        children = [
            child
            for child in glyph_like
            if child is not box and _contains(box, child) and child.area < int(box.area * 0.88)
        ]
        parts = _nonoverlap_x(_nms(children, 0.5), 0.38)
        if len(parts) >= 2:
            continue
        keep.append(box)
    keep = _nms(keep, 0.45)
    if keep:
        return sorted(keep, key=lambda box: box.x1)
    wide = [box for box in sized if box.width > max_w]
    if wide:
        return [max(wide, key=lambda box: box.area)]
    return []


def _count_from_aspect(width: int, height: int) -> int:
    return int(round(width / max(8.0, _GLYPH_ASPECT * max(height, 1))))


def _is_wide(box: GlyphBox, cell_height: int) -> bool:
    ref_h = max(box.height, int(cell_height * 0.85))
    return box.width >= max(10, int(round(_WIDE_ASPECT * ref_h)))


def _expected_glyph_count(
    filled: np.ndarray,
    blocks: list[tuple[int, int]],
) -> int:
    height, width = filled.shape
    guess = 0
    for x1, x2 in blocks or [(0, width)]:
        span = max(1, x2 - x1)
        box = GlyphBox(x1, 0, x2, height)
        if _is_wide(box, height):
            local_necks = _neck_cuts(filled[:, x1:x2])
            n = len(local_necks) + 1 if local_necks else 1
            guess += max(n, _count_from_aspect(span, height), 2)
        else:
            guess += 1
    return int(np.clip(max(guess, 1), _MIN_GLYPHS, _MAX_GLYPHS))


def _vertical_blocks(filled: np.ndarray) -> list[tuple[int, int]]:
    """Ink spans separated by almost-empty columns. Necks of ligatures stay inside a block."""

    width = filled.shape[1]
    proj = _smooth(_column_ink(filled))
    peak = float(proj.max()) if proj.size else 0.0
    if peak < 2:
        return [(0, width)]
    thresh = max(1.0, peak * 0.08)
    ink = proj > thresh
    blocks: list[tuple[int, int]] = []
    x = 0
    min_w = max(3, width // 24)
    while x < width:
        if not ink[x]:
            x += 1
            continue
        start = x
        while x < width and ink[x]:
            x += 1
        if x - start >= min_w:
            blocks.append((start, x))
    return blocks or [(0, width)]


def _merge_close_blocks(blocks: list[tuple[int, int]], height: int) -> list[tuple[int, int]]:
    """Join fragments of one digit (open 4/5) across a tiny gap, not two letters."""

    if len(blocks) < 2:
        return blocks
    max_gap = max(2, int(round(height * 0.10)))
    max_w = max(8, int(round(height * 0.92)))
    merged = [blocks[0]]
    for x1, x2 in blocks[1:]:
        prev_x1, prev_x2 = merged[-1]
        gap = x1 - prev_x2
        combined = x2 - prev_x1
        if 0 <= gap <= max_gap and combined <= max_w:
            merged[-1] = (prev_x1, x2)
        else:
            merged.append((x1, x2))
    return merged


def _usable_cuts(cuts: list[int], width: int, min_part: int) -> list[int]:
    """Drop valleys that would leave a sliver too thin to be a chess glyph."""

    kept: list[int] = []
    prev = 0
    for cut in sorted(cuts):
        if cut - prev >= min_part and width - cut >= min_part:
            kept.append(cut)
            prev = cut
    return kept


def _neck_cuts(binary: np.ndarray, *, frac: float = 0.55) -> list[int]:
    """Interior projection valleys with a real ink peak on both sides (ligature necks)."""

    proj = _smooth(_column_ink(binary), radius=1)
    width = int(proj.size)
    if width < 12:
        return []
    peak = float(proj.max())
    if peak < 2:
        return []
    lo = max(3, width * 14 // 100)
    hi = min(width - 3, width * 86 // 100)
    min_sep = max(4, width // 14)
    cuts: list[int] = []
    x = lo
    while x < hi:
        if proj[x] > proj[x - 1] or proj[x] > proj[x + 1]:
            x += 1
            continue
        start = x
        while x < hi and proj[x] <= proj[start] + 1e-3:
            x += 1
        valley = (start + x - 1) // 2
        left_peak = float(proj[:valley].max())
        right_peak = float(proj[valley + 1 :].max())
        if left_peak < peak * 0.28 or right_peak < peak * 0.28:
            continue
        if float(proj[valley]) <= frac * min(left_peak, right_peak):
            if not cuts or valley - cuts[-1] >= min_sep:
                cuts.append(int(valley))
    min_part = max(6, int(round(binary.shape[0] * 0.32)))
    return _usable_cuts(cuts, width, min_part)


def _choose_boxes(
    binary: np.ndarray,
    filled: np.ndarray,
    mser: list[GlyphBox],
    blocks: list[tuple[int, int]],
    expected: int,
) -> list[GlyphBox]:
    """True vertical gaps first. Necks / MSER leaves split a connected block."""

    height, width = binary.shape
    necks = _neck_cuts(filled)
    if len(necks) + 1 == expected and expected >= 2:
        ranges = _ranges_from_cuts(width, necks)
        boxes = [_tight_box(filled[:, x1:x2], x1, 0) for x1, x2 in ranges]
        boxes = [box for box in boxes if box is not None]
        if len(boxes) == expected:
            return _snap_to_mser(boxes, mser)

    boxes: list[GlyphBox] = []
    for x1, x2 in blocks or [(0, width)]:
        box = _tight_box(filled[:, x1:x2], x1, 0)
        if box is None:
            continue
        local = filled[:, box.x1 : box.x2]
        local_necks = [box.x1 + cut for cut in _neck_cuts(local)]
        inner = [item for item in mser if _contains(box, item, frac=0.75)]
        if len(local_necks) >= 1:
            local_rel = [cut - box.x1 for cut in local_necks]
            parts = []
            for a, b in _ranges_from_cuts(box.width, local_rel):
                part = _tight_box(filled[:, box.x1 + a : box.x1 + b], box.x1 + a, 0)
                if part is not None:
                    parts.append(part)
            if len(parts) >= 2:
                boxes.extend(parts)
                continue
        if _is_wide(box, height) and _is_good_partition(inner, max(2, _count_from_aspect(box.width, height)), box.width):
            boxes.extend(sorted(inner, key=lambda item: item.x1))
            continue
        boxes.append(box)
    if not boxes:
        boxes = [GlyphBox(0, 0, width, height)]
    boxes = _snap_to_mser(boxes, mser)
    if len(boxes) != expected:
        boxes = _match_expected(binary, boxes, expected, mser)
    return boxes


def _ranges_from_cuts(width: int, cuts: list[int]) -> list[tuple[int, int]]:
    edges = [0] + sorted(set(cut for cut in cuts if 1 < cut < width - 1)) + [width]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _is_good_partition(boxes: list[GlyphBox], expected: int, width: int) -> bool:
    if len(boxes) != expected:
        return False
    ordered = sorted(boxes, key=lambda box: box.x1)
    min_w = max(3, round(width * _MIN_WIDTH_FRAC * 0.7))
    max_w = max(min_w + 1, round(width * _MAX_WIDTH_FRAC * 1.15))
    if any(box.width < min_w or box.width > max_w for box in ordered):
        return False
    for left, right in zip(ordered, ordered[1:]):
        if right.x1 + 2 < left.x2 - max(2, left.width // 5):
            return False
    span = ordered[-1].x2 - ordered[0].x1
    return span >= width * 0.55


def _snap_to_mser(boxes: list[GlyphBox], mser: list[GlyphBox]) -> list[GlyphBox]:
    if not mser or not boxes:
        return boxes
    edges = sorted({box.x1 for box in mser} | {box.x2 for box in mser})
    snapped: list[GlyphBox] = []
    for box in boxes:
        x1 = _nearest_edge(box.x1, edges, max(3, box.width // 6))
        x2 = _nearest_edge(box.x2, edges, max(3, box.width // 6))
        if x2 - x1 >= 3:
            snapped.append(GlyphBox(x1, box.y1, x2, box.y2))
        else:
            snapped.append(box)
    return snapped


def _nearest_edge(value: int, edges: list[int], limit: int) -> int:
    best = value
    best_dist = limit + 1
    for edge in edges:
        dist = abs(edge - value)
        if dist < best_dist:
            best_dist = dist
            best = edge
    return best if best_dist <= limit else value


def _match_expected(
    binary: np.ndarray,
    boxes: list[GlyphBox],
    expected: int,
    mser: list[GlyphBox],
) -> list[GlyphBox]:
    current = sorted(boxes, key=lambda box: box.x1)
    width = binary.shape[1]
    while len(current) < expected:
        index = max(range(len(current)), key=lambda i: current[i].width)
        box = current[index]
        if box.width < max(10, round(width * _MIN_WIDTH_FRAC * 2)):
            break
        remaining = expected - len(current) + 1
        cut = _best_cut(binary[:, box.x1 : box.x2], 1.0 / remaining, mser, box.x1)
        cut = int(np.clip(cut, box.x1 + 4, box.x2 - 4))
        left = _tight_box(binary[:, box.x1 : cut], box.x1, 0)
        right = _tight_box(binary[:, cut : box.x2], cut, 0)
        if left is None or right is None:
            break
        current = current[:index] + [left, right] + current[index + 1 :]
    while len(current) > expected:
        costs: list[tuple[float, int]] = []
        for i in range(len(current) - 1):
            left, right = current[i], current[i + 1]
            gap = max(0, right.x1 - left.x2)
            combined = right.x2 - left.x1
            costs.append((gap + combined * 0.01, i))
        _, index = min(costs)
        left, right = current[index], current[index + 1]
        merged = GlyphBox(
            min(left.x1, right.x1),
            min(left.y1, right.y1),
            max(left.x2, right.x2),
            max(left.y2, right.y2),
        )
        current = current[:index] + [merged] + current[index + 2 :]
    return current


def _best_cut(binary: np.ndarray, fraction: float, mser: list[GlyphBox], origin_x: int) -> int:
    """Cut a connected blob at a thin vertical neck near the expected fraction."""

    height, width = binary.shape
    proj = _smooth(_column_ink(binary), radius=1)
    peak = max(float(proj.max()), 1.0)
    target = int(round(width * fraction))
    lo = max(3, int(width * 0.16))
    hi = min(width - 3, int(width * 0.84))
    best_x = min(max(target, lo), hi)
    best_cost = 1e9
    mser_local = [box.x1 - origin_x for box in mser] + [box.x2 - origin_x for box in mser]
    for x in range(lo, hi):
        neck = _stroke_frac(binary, x)
        gap = float(proj[x]) / peak
        bias = abs(x - target) / max(width, 1)
        fall = _drop_fall_thickness(binary, x)
        snap = 0.0
        if mser_local:
            snap = min(abs(x - edge) for edge in mser_local) / max(width, 1)
        cost = 0.34 * gap + 0.28 * neck + 0.16 * fall + 0.12 * bias + 0.10 * snap
        if cost < best_cost:
            best_cost = cost
            best_x = x
    return origin_x + best_x


def _stroke_frac(binary: np.ndarray, x: int) -> float:
    column = binary[:, x] > 0
    if not np.any(column):
        return 0.0
    longest = 0
    run = 0
    for pixel in column:
        if pixel:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest / max(binary.shape[0], 1)


def _drop_fall_thickness(binary: np.ndarray, x0: int) -> float:
    height, width = binary.shape
    x = int(np.clip(x0, 0, width - 1))
    ink = 0
    for y in range(height):
        options = [c for c in (x - 1, x, x + 1) if 0 <= c < width]
        x = min(options, key=lambda c: (int(binary[y, c] > 0), abs(c - x0)))
        ink += int(binary[y, x] > 0)
    return ink / max(height, 1)


def _tight_box(strip: np.ndarray, origin_x: int, origin_y: int) -> GlyphBox | None:
    if strip.size == 0:
        return None
    ys, xs = np.where(strip > 0)
    if len(xs) < 4:
        return None
    return GlyphBox(
        origin_x + int(xs.min()),
        origin_y + int(ys.min()),
        origin_x + int(xs.max()) + 1,
        origin_y + int(ys.max()) + 1,
    )


def _drop_tiny(boxes: list[GlyphBox], content: GlyphBox) -> list[GlyphBox]:
    min_h = max(6, round(content.height * 0.32))
    min_w = max(3, round(content.width * 0.07))
    return [box for box in boxes if box.height >= min_h and box.width >= min_w]


def _merge_box_fragments(boxes: list[GlyphBox], content_width: int, content_height: int) -> list[GlyphBox]:
    if len(boxes) < 2:
        return boxes
    ordered = sorted(boxes, key=lambda box: box.x1)
    merged: list[GlyphBox] = [ordered[0]]
    max_w = max(8, int(round(content_width * _MAX_WIDTH_FRAC)))
    sliver = max(4, int(round(content_height * 0.22)))
    one_letter = max(sliver, int(round(content_height * 1.18)))
    for box in ordered[1:]:
        prev = merged[-1]
        overlap = _x_overlap(prev, box)
        combined = GlyphBox(
            min(prev.x1, box.x1),
            min(prev.y1, box.y1),
            max(prev.x2, box.x2),
            max(prev.y2, box.y2),
        )
        stacked = overlap >= 0.55 and combined.width <= max(prev.width, box.width) + 2
        absorb = (
            min(prev.width, box.width) <= sliver
            and combined.width <= one_letter
            and combined.width <= max_w
        )
        if (stacked or absorb) and combined.width <= max(max_w, one_letter):
            merged[-1] = combined
        else:
            merged.append(box)
    return merged


def _x_overlap(left: GlyphBox, right: GlyphBox) -> float:
    x1 = max(left.x1, right.x1)
    x2 = min(left.x2, right.x2)
    inter = max(0, x2 - x1)
    return inter / max(1, min(left.width, right.width))


def _contains(outer: GlyphBox, inner: GlyphBox, frac: float = 0.82) -> bool:
    x1 = max(outer.x1, inner.x1)
    y1 = max(outer.y1, inner.y1)
    x2 = min(outer.x2, inner.x2)
    y2 = min(outer.y2, inner.y2)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter >= frac * max(inner.area, 1)


def _unique_boxes(boxes: list[GlyphBox], tol: int = 2) -> list[GlyphBox]:
    unique: list[GlyphBox] = []
    for box in sorted(boxes, key=lambda item: (-item.area, item.x1)):
        if any(
            abs(box.x1 - other.x1) <= tol
            and abs(box.x2 - other.x2) <= tol
            and abs(box.y1 - other.y1) <= tol
            and abs(box.y2 - other.y2) <= tol
            for other in unique
        ):
            continue
        unique.append(box)
    return unique


def _nms(boxes: list[GlyphBox], iou: float) -> list[GlyphBox]:
    ordered = sorted(boxes, key=lambda box: box.area, reverse=True)
    keep: list[GlyphBox] = []
    for box in ordered:
        if any(_iou(box, other) >= iou for other in keep):
            continue
        keep.append(box)
    return keep


def _iou(left: GlyphBox, right: GlyphBox) -> float:
    x1 = max(left.x1, right.x1)
    y1 = max(left.y1, right.y1)
    x2 = min(left.x2, right.x2)
    y2 = min(left.y2, right.y2)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = left.area + right.area - inter
    return inter / max(union, 1)


def _nonoverlap_x(boxes: list[GlyphBox], max_overlap: float) -> list[GlyphBox]:
    ordered = sorted(boxes, key=lambda box: box.x1)
    picked: list[GlyphBox] = []
    for box in ordered:
        if picked and _x_overlap(picked[-1], box) > max_overlap:
            continue
        picked.append(box)
    return picked


def _column_ink(binary: np.ndarray) -> np.ndarray:
    return (binary > 0).sum(axis=0).astype(np.float32)


def _smooth(proj: np.ndarray, radius: int = 2) -> np.ndarray:
    kernel = max(3, 2 * radius + 1)
    return cv2.GaussianBlur(proj.reshape(1, -1), (kernel, 1), 0).ravel()


def _tile(images: list[np.ndarray], *, cols: int) -> np.ndarray:
    cell_h = max(item.shape[0] for item in images)
    cell_w = max(item.shape[1] for item in images)
    rows = (len(images) + cols - 1) // cols
    montage = np.full((rows * cell_h, cols * cell_w, 3), 30, dtype=np.uint8)
    for index, image in enumerate(images):
        row, col = divmod(index, cols)
        y, x = row * cell_h, col * cell_w
        h, w = image.shape[:2]
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        montage[y : y + h, x : x + w] = image
    return montage
