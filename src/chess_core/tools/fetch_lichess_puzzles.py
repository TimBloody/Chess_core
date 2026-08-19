"""Build a small Lichess puzzle CSV without downloading the 1.5GB dump.

By default reads a Hugging Face datasets-server page (CC0) or a local JSON
extract, keeps only lines that our classic engine can play, and writes
``src/chess_core/data/puzzles/lichess_mini.csv``.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from chess_core.app.puzzles import (
    LichessPuzzle,
    format_lichess_csv,
    parse_lichess_json,
    puzzle_line_is_legal,
)
from chess_core.infra.paths import puzzles_dir
from chess_core.infra.storage.lichess_puzzles import MINI_CSV_NAME
from chess_core.modes.chess import classic_chess

_HF_ROWS = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=Lichess/chess-puzzles&config=default&split=train"
)
_USER_AGENT = "Chess_core/0.0.1 (mini puzzle extract; no full dump)"
_PREFERRED_THEMES = frozenset(
    {
        "mateIn1",
        "mateIn2",
        "fork",
        "pin",
        "skewer",
        "discoveredAttack",
        "hangingPiece",
        "backRankMate",
        "sacrifice",
        "attraction",
    }
)


def fetch_hf_rows(offsets: tuple[int, ...], page_size: int = 100) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for offset in offsets:
        url = f"{_HF_ROWS}&offset={offset}&length={page_size}"
        request = urllib.request.Request(
            url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode())
        for item in payload.get("rows", ()):
            row = item.get("row") or {}
            puzzle_id = str(row.get("PuzzleId") or "")
            if not puzzle_id or puzzle_id in seen:
                continue
            seen.add(puzzle_id)
            rows.append(row)
    return rows


def rows_to_puzzles(rows: list[dict]) -> list[LichessPuzzle]:
    return parse_lichess_json(json.dumps(rows))


def select_mini_set(
    puzzles: list[LichessPuzzle], *, limit: int = 60
) -> list[LichessPuzzle]:
    mode = classic_chess()
    legal = [puzzle for puzzle in puzzles if puzzle_line_is_legal(mode, puzzle)]
    legal.sort(key=_priority, reverse=True)
    chosen: list[LichessPuzzle] = []
    seen: set[str] = set()
    buckets = {
        "easy": [item for item in legal if item.rating and item.rating < 1200],
        "medium": [item for item in legal if 1200 <= item.rating < 1800],
        "hard": [item for item in legal if item.rating >= 1800],
    }
    quotas = {"easy": max(1, limit // 3), "medium": max(1, limit // 2), "hard": max(1, limit // 6)}
    for name, quota in quotas.items():
        for puzzle in buckets[name]:
            if puzzle.puzzle_id in seen:
                continue
            chosen.append(puzzle)
            seen.add(puzzle.puzzle_id)
            if sum(1 for item in chosen if _bucket(item) == name) >= quota:
                break
            if len(chosen) >= limit:
                break
        if len(chosen) >= limit:
            break
    if len(chosen) < limit:
        for puzzle in legal:
            if puzzle.puzzle_id in seen:
                continue
            chosen.append(puzzle)
            seen.add(puzzle.puzzle_id)
            if len(chosen) >= limit:
                break
    mates = [item for item in chosen if "mateIn1" in item.themes]
    rest = [item for item in chosen if item not in mates]
    return [*mates, *rest][:limit]


def _bucket(puzzle: LichessPuzzle) -> str:
    if puzzle.rating < 1200:
        return "easy"
    if puzzle.rating < 1800:
        return "medium"
    return "hard"


def _priority(puzzle: LichessPuzzle) -> tuple[int, int, int, int]:
    theme_hit = 1 if _PREFERRED_THEMES.intersection(puzzle.themes) else 0
    short = 1 if len(puzzle.solution_uci) <= 3 else 0
    return (theme_hit, short, puzzle.popularity, puzzle.nb_plays)


def write_mini_csv(puzzles: list[LichessPuzzle], path: Path | None = None) -> Path:
    target = path or puzzles_dir() / MINI_CSV_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(format_lichess_csv(puzzles), encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-json",
        type=Path,
        help="Local HF-style JSON list (skip network)",
    )
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="CSV path (default: bundled lichess_mini.csv)",
    )
    args = parser.parse_args()
    if args.from_json is not None:
        payload = json.loads(args.from_json.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("puzzles", [])
        puzzles = rows_to_puzzles(rows)
    else:
        puzzles = rows_to_puzzles(fetch_hf_rows((0, 800, 2500, 7000, 15000)))
    selected = select_mini_set(puzzles, limit=args.limit)
    path = write_mini_csv(selected, args.output)
    print(f"wrote {len(selected)} puzzles to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
