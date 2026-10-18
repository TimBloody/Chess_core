"""Chess glyph charset and MNIST invert, without CUDA training."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

np = pytest.importorskip("numpy")

from chess_core.app.experiments.ocr_glyphs import (
    CHARSET,
    CYRILLIC_LETTERS,
    DIGITS,
    LATIN_LETTERS,
    add_strikethrough,
    augment_mnist_glyph,
    class_weights,
    fold_read_char,
    collect_cyrillic_paths,
    emnist_byclass_index,
    emnist_keep_indices,
    invert_to_dark_ink,
    make_glyph_cnn,
    missing_cyrillic,
    thicken_strokes,
    thin_strokes,
    to_mnist_glyph,
    weights_dir,
)


def test_charset_is_single_glyphs_not_kr() -> None:
    from chess_core.ocr.roles import ROLE_IDS

    assert CHARSET == ROLE_IDS
    assert "Кр" not in CHARSET
    assert LATIN_LETTERS == tuple("abcdefghNKBRQxO")
    assert "HASH" in CHARSET
    assert "BS" in CHARSET
    assert "f_c" in CHARSET
    assert CYRILLIC_LETTERS == ("Л", "Ф", "р")
    assert DIGITS == tuple("12345678")
    assert "0" not in CHARSET and "9" not in CHARSET


def test_emnist_byclass_indices() -> None:
    assert emnist_byclass_index("1") == 1
    assert emnist_byclass_index("8") == 8
    assert emnist_byclass_index("A") == 10
    assert emnist_byclass_index("B") == 11
    assert emnist_byclass_index("N") == 23
    assert emnist_byclass_index("O") == 24
    assert emnist_byclass_index("a") == 36
    assert emnist_byclass_index("h") == 43
    assert emnist_byclass_index("x") == 59
    keep = emnist_keep_indices()
    assert keep[40] == "f_e"
    assert keep[23] == "KN"
    assert keep[emnist_byclass_index("K")] == "KN"
    assert keep[emnist_byclass_index("C")] == "BS"
    assert keep[emnist_byclass_index("c")] == "f_c"
    assert keep[emnist_byclass_index("B")] == "BS"
    assert keep[emnist_byclass_index("b")] == "f_b"
    assert keep[emnist_byclass_index("0")] == "O"
    assert emnist_byclass_index("9") not in keep


def test_invert_makes_dark_ink_on_white() -> None:
    tile = np.zeros((28, 28), dtype=np.uint8)
    tile[8:20, 10:18] = 255
    inverted = invert_to_dark_ink(tile)
    assert int(inverted[0, 0]) == 255
    assert int(inverted[12, 14]) == 0
    glyph = to_mnist_glyph(tile, invert=True)
    assert glyph.shape == (28, 28)
    assert int(glyph[0, 0]) == 255
    assert int(glyph.min()) < 175


def test_invert_does_not_transpose_an_upright_bar() -> None:
    tile = np.zeros((28, 28), dtype=np.uint8)
    tile[:, 6:10] = 255
    glyph = to_mnist_glyph(tile, invert=True)
    ys, xs = np.where(glyph < 175)
    assert int(ys.max() - ys.min()) > int(xs.max() - xs.min())


def test_class_weights_boost_rare_labels() -> None:
    labels = np.array([0] * 10 + [1] * 2, dtype=np.int64)
    weights = class_weights(labels, 2)
    assert weights[1] > weights[0]


def test_collects_cyrillic_folders(tmp_path) -> None:
    for letter in ("Л", "Ф", "Р"):
        folder = tmp_path / "Cyrillic" / letter
        folder.mkdir(parents=True)
        (folder / "0.png").write_bytes(b"not-an-image")
    found = collect_cyrillic_paths(tmp_path)
    assert len(found["RK"]) == 1
    assert len(found["QN"]) == 1
    assert len(found["ER"]) == 1
    assert missing_cyrillic({}) == ("RK", "QN", "ER")


def _bar_tile() -> np.ndarray:
    tile = np.full((28, 28), 255, dtype=np.uint8)
    tile[6:22, 12:16] = 20
    return tile


def test_thicken_and_thin_change_ink_mass() -> None:
    tile = _bar_tile()
    thick = thicken_strokes(tile, size=3)
    thin = thin_strokes(tile, size=2)
    assert int(np.sum(thick < 180)) > int(np.sum(tile < 180))
    assert int(np.sum(thin < 180)) < int(np.sum(tile < 180))


def test_strikethrough_adds_a_stroke() -> None:
    tile = _bar_tile()
    struck = add_strikethrough(tile, np.random.default_rng(0))
    assert struck.shape == (28, 28)
    assert int(np.sum(struck < 180)) > int(np.sum(tile < 180))


def test_augment_keeps_mnist_canvas() -> None:
    out = augment_mnist_glyph(_bar_tile(), np.random.default_rng(1), strikethrough_p=1.0)
    assert out.shape == (28, 28)
    assert out.dtype == np.uint8
    assert int(out[0, 0]) > 180
    assert int(out.min()) < 180


def test_c_and_C_are_different_roles() -> None:
    from chess_core.ocr.roles import canonicalize

    assert canonicalize("c") == "f_c"
    assert canonicalize("C") == "BS"
    assert fold_read_char("C") == "C"
    assert fold_read_char("c") == "c"


def test_cnn_forward_shape() -> None:
    torch = pytest.importorskip("torch")
    model = make_glyph_cnn(torch, len(CHARSET))
    logits = model(torch.zeros(2, 1, 28, 28))
    assert tuple(logits.shape) == (2, len(CHARSET))


def test_trained_cnn_reads_printed_e() -> None:
    torch = pytest.importorskip("torch")
    cv2 = pytest.importorskip("cv2")
    from chess_core.app.experiments.ocr_glyphs import load_glyph_recognizer, predict_mnist_tiles
    from chess_core.app.experiments.ocr_mser import mnist_pad

    if not (weights_dir() / "glyph_cnn.pt").is_file():
        pytest.skip("нет glyph_cnn.pt")
    canvas = np.full((64, 64), 255, dtype=np.uint8)
    cv2.putText(canvas, "e", (12, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 2, cv2.LINE_AA)
    model, charset, device = load_glyph_recognizer()
    char, score, _alts = predict_mnist_tiles([mnist_pad(canvas)], model, charset, device)[0]
    assert char in charset
    assert score > 0.0
    del torch
