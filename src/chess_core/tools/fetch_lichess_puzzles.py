"""Sample a multi-theme Lichess puzzle catalog from the official dump.

The full CSV is huge; this streams ``lichess_db_puzzle.csv.zst`` and keeps a
few thousand popular puzzles stratified by theme. Output is CC0, same as the
source: https://database.lichess.org/#puzzles

Usage::

    python -m chess_core.tools.fetch_lichess_puzzles
    python -m chess_core.tools.fetch_lichess_puzzles --from-csv dump.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path

from chess_core.app.puzzles import (
    LichessPuzzle,
    format_lichess_csv,
    lichess_puzzle_from_csv_row,
)
from chess_core.infra.paths import puzzles_dir
from chess_core.infra.storage.lichess_puzzles import CATALOG_CSV_NAME

LICHESS_DUMP_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

# Primary bucket first wins, so mate-in-1 does not swallow every "mate" fork.
THEME_QUOTAS: dict[str, int] = {
    "mateIn1": 400,
    "mateIn2": 400,
    "mateIn3": 250,
    "mateIn4": 80,
    "fork": 300,
    "pin": 250,
    "skewer": 200,
    "discoveredAttack": 200,
    "hangingPiece": 200,
    "sacrifice": 200,
    "attraction": 150,
    "deflection": 150,
    "trappedPiece": 150,
    "backRankMate": 150,
    "exposedKing": 120,
    "doubleCheck": 80,
    "capturingDefender": 120,
    "advancedPawn": 100,
    "quietMove": 100,
    "kingsideAttack": 120,
    "clearance": 80,
    "xRayAttack": 80,
    "intermezzo": 80,
    "crushing": 180,
    "advantage": 150,
}

DEFAULT_MIN_POPULARITY = 70
DEFAULT_MIN_PLAYS = 40
DEFAULT_RATING_MIN = 600
DEFAULT_RATING_MAX = 2200


def sample_lichess_rows(
    rows: Iterable[Mapping[str, str]],
    *,
    quotas: Mapping[str, int] | None = None,
    min_popularity: int = DEFAULT_MIN_POPULARITY,
    min_plays: int = DEFAULT_MIN_PLAYS,
    rating_min: int = DEFAULT_RATING_MIN,
    rating_max: int = DEFAULT_RATING_MAX,
) -> list[LichessPuzzle]:
    """Fill per-theme quotas from an official-dump CSV row iterator."""

    remaining = dict(quotas or THEME_QUOTAS)
    chosen: list[LichessPuzzle] = []
    seen: set[str] = set()
    scanned = 0
    for row in rows:
        scanned += 1
        if scanned % 100_000 == 0:
            filled = sum(1 for count in remaining.values() if count <= 0)
            print(
                f"scanned {scanned:,} rows, kept {len(chosen)}, "
                f"quotas full {filled}/{len(remaining)}",
                file=sys.stderr,
            )
        if all(count <= 0 for count in remaining.values()):
            break
        puzzle = lichess_puzzle_from_csv_row(row)
        if puzzle is None or puzzle.puzzle_id in seen:
            continue
        if puzzle.popularity < min_popularity or puzzle.nb_plays < min_plays:
            continue
        if not rating_min <= puzzle.rating <= rating_max:
            continue
        bucket = next(
            (
                theme
                for theme in remaining
                if remaining[theme] > 0 and theme in puzzle.themes
            ),
            None,
        )
        if bucket is None:
            continue
        remaining[bucket] -= 1
        seen.add(puzzle.puzzle_id)
        chosen.append(puzzle)
    return chosen


def write_catalog(puzzles: Sequence[LichessPuzzle], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_lichess_csv(puzzles), encoding="utf-8")


def iter_csv_rows(text_stream: io.TextIOBase) -> Iterator[dict[str, str]]:
    reader = csv.DictReader(text_stream)
    for row in reader:
        yield {key: value or "" for key, value in row.items() if key is not None}


def _open_zst_url(url: str):
    try:
        import zstandard as zstd
    except ImportError as exc:
        raise SystemExit(
            "Need the zstandard package to stream the Lichess dump. "
            "Install it with: python -m pip install zstandard"
        ) from exc

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Chess_core puzzle sampler"},
    )
    response = urllib.request.urlopen(request)  # noqa: S310 — official Lichess dump
    decompressor = zstd.ZstdDecompressor()
    return response, decompressor.stream_reader(response)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=LICHESS_DUMP_URL,
        help="Official .csv.zst dump URL",
    )
    parser.add_argument(
        "--from-csv",
        type=Path,
        help="Sample from an already-decompressed official CSV instead of downloading",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=puzzles_dir() / CATALOG_CSV_NAME,
        help="Destination CSV (default: bundled data/puzzles/lichess_catalog.csv)",
    )
    parser.add_argument("--min-popularity", type=int, default=DEFAULT_MIN_POPULARITY)
    parser.add_argument("--min-plays", type=int, default=DEFAULT_MIN_PLAYS)
    parser.add_argument("--rating-min", type=int, default=DEFAULT_RATING_MIN)
    parser.add_argument("--rating-max", type=int, default=DEFAULT_RATING_MAX)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.from_csv is not None:
        with args.from_csv.open(encoding="utf-8", newline="") as handle:
            puzzles = sample_lichess_rows(
                iter_csv_rows(handle),
                min_popularity=args.min_popularity,
                min_plays=args.min_plays,
                rating_min=args.rating_min,
                rating_max=args.rating_max,
            )
    else:
        print(f"Downloading {args.url} …", file=sys.stderr)
        response, reader = _open_zst_url(args.url)
        try:
            text = io.TextIOWrapper(reader, encoding="utf-8")
            puzzles = sample_lichess_rows(
                iter_csv_rows(text),
                min_popularity=args.min_popularity,
                min_plays=args.min_plays,
                rating_min=args.rating_min,
                rating_max=args.rating_max,
            )
        finally:
            reader.close()
            response.close()
    write_catalog(puzzles, args.output)
    print(f"Wrote {len(puzzles)} puzzles to {args.output}", file=sys.stderr)
    return 0 if puzzles else 1


if __name__ == "__main__":
    raise SystemExit(main())
