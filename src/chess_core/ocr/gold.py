"""Hand-labelled scoresheet plies under data/gold/<sheet_id>.json."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from chess_core.infra.paths import project_root


def gold_dir() -> Path:
    return project_root() / "data" / "gold"


@dataclass(frozen=True, slots=True)
class GoldSheet:
    sheet_id: str
    plies: tuple[str, ...]
    chars: tuple[tuple[str, ...], ...]
    path: Path
    source: str
    note: str = ""
    notes: str = ""
    ambiguous: bool = False

    @property
    def n_plies(self) -> int:
        return len(self.plies)


def load_gold(sheet_id: str | Path) -> GoldSheet | None:
    stem = Path(sheet_id).stem
    path = gold_dir() / f"{stem}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    plies = tuple(str(item) for item in (data.get("plies") or ()) if str(item))
    chars_raw = data.get("chars") or ()
    chars = tuple(tuple(str(ch) for ch in row) for row in chars_raw)
    return GoldSheet(
        sheet_id=stem,
        plies=plies,
        chars=chars,
        path=path,
        source=str(data.get("source") or stem),
        note=str(data.get("note") or data.get("notes") or ""),
        notes=str(data.get("notes") or data.get("note") or ""),
        ambiguous=bool(data.get("ambiguous") or False),
    )


def list_gold_ids() -> tuple[str, ...]:
    root = gold_dir()
    if not root.is_dir():
        return ()
    found: list[str] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("plies"):
            found.append(path.stem)
    return tuple(found)
