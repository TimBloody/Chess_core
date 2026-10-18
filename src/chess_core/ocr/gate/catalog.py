"""On-disk gate crop catalog. Holdout paths never appear in train lists."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from chess_core.infra.paths import project_root


def gate_root() -> Path:
    return project_root() / "data" / "gate"


def labels_path() -> Path:
    return gate_root() / "labels.json"


def split_path() -> Path:
    return gate_root() / "split.json"


@dataclass(frozen=True, slots=True)
class CropRecord:
    path: str
    norm_path: str
    label: int
    source_sheet: str
    cell: str
    bbox: list[int]
    hard_case: bool
    split: str
    notes: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_catalog(path: Path | None = None) -> list[CropRecord]:
    target = path or labels_path()
    if not target.is_file():
        return []
    rows = json.loads(target.read_text(encoding="utf-8"))
    return [CropRecord(**row) for row in rows]


def save_catalog(rows: Sequence[CropRecord], path: Path | None = None) -> Path:
    target = path or labels_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([row.to_dict() for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def train_rows(rows: Iterable[CropRecord]) -> tuple[CropRecord, ...]:
    return tuple(row for row in rows if row.split == "train")


def holdout_rows(rows: Iterable[CropRecord]) -> tuple[CropRecord, ...]:
    return tuple(row for row in rows if row.split == "holdout")


def assert_sheet_disjoint(rows: Sequence[CropRecord]) -> None:
    train = {row.source_sheet for row in rows if row.split == "train"}
    hold = {row.source_sheet for row in rows if row.split == "holdout"}
    overlap = train & hold
    if overlap:
        raise AssertionError(f"gate sheets leak train∩holdout={sorted(overlap)}")


def assert_holdout_unused_by_fit(fit_paths: Sequence[str], rows: Sequence[CropRecord]) -> None:
    hold = {row.path for row in rows if row.split == "holdout"}
    leak = set(fit_paths) & hold
    if leak:
        raise AssertionError(f"holdout crops used in fit: {len(leak)}")
