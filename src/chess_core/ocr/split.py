"""Writer-disjoint split records. Oversampling happens only on train after this file is written."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from chess_core.infra.paths import project_root


def splits_dir() -> Path:
    return project_root() / "data" / "splits"


def tile_hash(tile: np.ndarray) -> str:
    array = np.ascontiguousarray(tile)
    return hashlib.sha256(array.tobytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SplitRecord:
    seed: int
    method: str
    train_writers: tuple[str, ...]
    val_writers: tuple[str, ...]
    train_hashes: tuple[str, ...]
    val_hashes: tuple[str, ...]
    oversampled_hashes: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "method": self.method,
            "train_writers": list(self.train_writers),
            "val_writers": list(self.val_writers),
            "n_train_hashes": len(self.train_hashes),
            "n_val_hashes": len(self.val_hashes),
            "train_hashes": list(self.train_hashes),
            "val_hashes": list(self.val_hashes),
            "oversampled_hashes": list(self.oversampled_hashes),
            "notes": list(self.notes),
        }


def assert_writer_disjoint(train: Iterable[str], val: Iterable[str]) -> None:
    overlap = set(train) & set(val)
    if overlap:
        raise AssertionError(f"writers leak train∩val={sorted(overlap)[:20]}")


def assert_hash_disjoint(train: Iterable[str], val: Iterable[str], extra: Iterable[str] = ()) -> None:
    val_set = set(val)
    leak = (set(train) | set(extra)) & val_set
    if leak:
        raise AssertionError(f"image hashes leak into val: {len(leak)}")


def write_split(record: SplitRecord, path: Path | None = None) -> Path:
    target = path or (splits_dir() / "p1_split.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_split(path: Path | None = None) -> dict[str, object]:
    target = path or (splits_dir() / "p1_split.json")
    return json.loads(target.read_text(encoding="utf-8"))


def hashes_of(tiles: Sequence[np.ndarray]) -> tuple[str, ...]:
    return tuple(tile_hash(tile) for tile in tiles)


def oversample_indices(
    labels: np.ndarray,
    *,
    min_count: int,
    cap: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Train-only. Cap frequent roles, repeat rare ones. Returns selected indices."""

    if labels.size == 0:
        return np.zeros(0, dtype=np.int64)
    chosen: list[np.ndarray] = []
    for cls in np.unique(labels):
        idx = np.where(labels == cls)[0]
        if idx.size == 0:
            continue
        if idx.size > cap:
            idx = rng.choice(idx, size=cap, replace=False)
        elif idx.size < min_count:
            extra = rng.choice(idx, size=min_count - idx.size, replace=True)
            idx = np.concatenate([idx, extra])
        chosen.append(idx)
    if not chosen:
        return np.zeros(0, dtype=np.int64)
    return np.concatenate(chosen)
