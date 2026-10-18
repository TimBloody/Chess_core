"""Writer-disjoint split and oversampling must not leak into val."""

from __future__ import annotations

import numpy as np
import pytest

from chess_core.ocr.split import (
    assert_hash_disjoint,
    assert_writer_disjoint,
    oversample_indices,
    tile_hash,
)


def test_writer_sets_do_not_overlap() -> None:
    train = ("w1", "w1", "w2")
    val = ("w3", "w4")
    assert_writer_disjoint(train, val)
    with pytest.raises(AssertionError):
        assert_writer_disjoint(("w1",), ("w1", "w2"))


def test_oversampled_tiles_have_no_val_copy() -> None:
    rng = np.random.default_rng(0)
    train_tiles = [rng.integers(0, 256, size=(28, 28), dtype=np.uint8) for _ in range(6)]
    val_tiles = [rng.integers(0, 256, size=(28, 28), dtype=np.uint8) for _ in range(4)]
    labels = np.array([0, 0, 0, 1, 1, 1], dtype=np.int64)
    picked = oversample_indices(labels, min_count=8, cap=4000, rng=rng)
    oversampled = [tile_hash(train_tiles[int(i)]) for i in picked]
    val_hashes = [tile_hash(tile) for tile in val_tiles]
    assert_hash_disjoint(oversampled, val_hashes)
    train_hashes = {tile_hash(tile) for tile in train_tiles}
    assert set(oversampled) <= train_hashes
    assert set(oversampled) & set(val_hashes) == set()
