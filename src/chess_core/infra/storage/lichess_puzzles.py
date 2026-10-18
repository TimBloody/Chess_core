"""Load Lichess puzzle catalogs from disk (CSV/JSON)."""

from __future__ import annotations

from pathlib import Path

from chess_core.app.puzzles import LichessPuzzle, parse_lichess_csv, parse_lichess_json
from chess_core.infra.paths import puzzles_dir

CATALOG_CSV_NAME = "lichess_catalog.csv"
MINI_CSV_NAME = "lichess_mini.csv"
COMPOSITION_CSV_NAME = "composition.csv"
CATALOG_CANDIDATES = (CATALOG_CSV_NAME, MINI_CSV_NAME)


def bundled_lichess_mini_path() -> Path:
    return puzzles_dir() / MINI_CSV_NAME


def bundled_lichess_catalog_path() -> Path:
    """Prefer the sampled multi-theme catalog, then the tiny mini extract."""

    directory = puzzles_dir()
    for name in CATALOG_CANDIDATES:
        path = directory / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return directory / MINI_CSV_NAME


def load_lichess_puzzles(path: Path | None = None) -> list[LichessPuzzle]:
    catalog = path or bundled_lichess_catalog_path()
    puzzles = _read_catalog(catalog)
    if path is None:
        extra = puzzles_dir() / COMPOSITION_CSV_NAME
        if extra.is_file():
            seen = {puzzle.puzzle_id for puzzle in puzzles}
            puzzles.extend(
                puzzle
                for puzzle in _read_catalog(extra)
                if puzzle.puzzle_id not in seen
            )
    return puzzles


def _read_catalog(catalog: Path) -> list[LichessPuzzle]:
    text = catalog.read_text(encoding="utf-8")
    suffix = catalog.suffix.lower()
    if suffix == ".json":
        return parse_lichess_json(text)
    return parse_lichess_csv(text)
