"""Load Lichess puzzle catalogs from disk (CSV/JSON)."""

from __future__ import annotations

from pathlib import Path

from chess_core.app.puzzles import LichessPuzzle, parse_lichess_csv, parse_lichess_json
from chess_core.infra.paths import puzzles_dir

MINI_CSV_NAME = "lichess_mini.csv"


def bundled_lichess_mini_path() -> Path:
    return puzzles_dir() / MINI_CSV_NAME


def load_lichess_puzzles(path: Path | None = None) -> list[LichessPuzzle]:
    catalog = path or bundled_lichess_mini_path()
    text = catalog.read_text(encoding="utf-8")
    suffix = catalog.suffix.lower()
    if suffix == ".json":
        return parse_lichess_json(text)
    return parse_lichess_csv(text)
