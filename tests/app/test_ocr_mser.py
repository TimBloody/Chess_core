"""Vertical-block glyph split and MNIST-style padding."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from chess_core.app.experiments.ocr_mser import glyph_boxes, mnist_pad, segment_cell


def _print_move(text: str, *, x: int = 12, scale: float = 1.15, thickness: int = 2) -> np.ndarray:
    canvas = np.full((72, 220), 255, dtype=np.uint8)
    cv2.putText(
        canvas,
        text,
        (x, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        0,
        thickness,
        cv2.LINE_AA,
    )
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def _connected_nf3() -> np.ndarray:
    """Nf3 with overlapping strokes so the letters share ink."""

    canvas = np.full((72, 200), 255, dtype=np.uint8)
    x = 8
    for char in "Nf3":
        cv2.putText(canvas, char, (x, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.35, 0, 3, cv2.LINE_AA)
        x += 16
    ink = cv2.dilate(255 - canvas, np.ones((3, 3), np.uint8), iterations=1)
    canvas = 255 - ink
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def test_splits_printed_e4_into_two() -> None:
    boxes = glyph_boxes(_print_move("e4"))
    assert len(boxes) == 2
    assert boxes[0].x2 <= boxes[1].x1 + 2


def test_splits_printed_nf3_into_three() -> None:
    boxes = glyph_boxes(_print_move("Nf3"))
    assert len(boxes) == 3


def test_splits_connected_nf3_into_three() -> None:
    boxes = glyph_boxes(_connected_nf3())
    assert len(boxes) == 3
    assert boxes[0].x1 < boxes[1].x1 < boxes[2].x1


def test_letter_e_is_one_glyph_despite_hole() -> None:
    boxes = glyph_boxes(_print_move("e"))
    assert len(boxes) == 1


def test_splits_printed_g4_into_two() -> None:
    boxes = glyph_boxes(_print_move("g4"))
    assert len(boxes) == 2
    assert boxes[0].width < boxes[0].height * 1.6


def test_mnist_pad_is_28_with_white_border() -> None:
    split = segment_cell(_print_move("e4"))
    assert split.glyphs
    for glyph in split.glyphs:
        canvas = glyph.mnist
        assert canvas.shape == (28, 28)
        assert int(canvas[0].min()) == 255
        assert int(canvas[-1].min()) == 255
        assert int(canvas[:, 0].min()) == 255
        assert int(canvas[:, -1].min()) == 255
        ys, xs = np.where(canvas < 175)
        assert ys.size
        longest = max(int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1))
        assert 16 <= longest <= 22


def test_mnist_pad_draws_margin_when_ink_touches_the_crop() -> None:
    patch = np.zeros((36, 14), dtype=np.uint8)
    canvas = mnist_pad(patch)
    assert canvas.shape == (28, 28)
    assert int(canvas[0, 0]) == 255
    assert int(canvas[-1, -1]) == 255
    ys, xs = np.where(canvas < 175)
    top, bottom = int(ys.min()), 27 - int(ys.max())
    left, right = int(xs.min()), 27 - int(xs.max())
    assert min(top, bottom, left, right) >= 3
    assert abs(top - bottom) <= 2
    assert abs(left - right) <= 2
    longest = max(int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1))
    assert longest == 20


def test_mnist_pad_centers_mass_of_a_corner_stroke() -> None:
    patch = np.full((90, 90), 255, dtype=np.uint8)
    patch[1:21, 1:9] = 0
    canvas = mnist_pad(patch)
    ys, xs = np.where(canvas < 175)
    assert abs(float(ys.mean()) - 13.5) < 2.0
    assert abs(float(xs.mean()) - 13.5) < 2.0
