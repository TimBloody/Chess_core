"""Combine PGN files into a multi-game PGN database.

Run in a directory containing exported games:
    python -m chess_core.tools.pgn_database
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from pathlib import Path


def collect_pgn_files(
    locations: Iterable[Path],
    *,
    recursive: bool = False,
    exclude: Path | None = None,
) -> list[Path]:
    excluded = exclude.resolve() if exclude is not None else None
    found: set[Path] = set()
    for raw_location in locations:
        location = raw_location.resolve()
        if location.is_file():
            candidates = (location,)
        elif location.is_dir():
            candidates = location.rglob("*.pgn") if recursive else location.glob("*.pgn")
        else:
            raise FileNotFoundError(location)
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved != excluded and not candidate.name.endswith(".tmp"):
                found.add(resolved)
    return sorted(found, key=lambda path: str(path).casefold())


def merge_pgn_files(sources: Sequence[Path], target: Path) -> tuple[Path, int]:
    if not sources:
        raise ValueError("no PGN files found")
    games: list[str] = []
    for source in sources:
        text = source.read_text(encoding="utf-8-sig").strip()
        if text:
            games.append(text)
    if not games:
        raise ValueError("all selected PGN files are empty")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text("\n\n".join(games) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(target)
    game_count = sum(text.count('[Event "') for text in games)
    return target, game_count or len(games)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Объединить PGN-файлы в базу, открываемую ChessBase."
    )
    parser.add_argument(
        "locations",
        nargs="*",
        type=Path,
        help="Файлы или директории (по умолчанию текущая директория).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("database.pgn"),
        help="Итоговая PGN-база (по умолчанию database.pgn).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Искать PGN также во вложенных директориях.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    locations = args.locations or [Path.cwd()]
    target = args.output.resolve()
    sources = collect_pgn_files(
        locations,
        recursive=args.recursive,
        exclude=target,
    )
    written, game_count = merge_pgn_files(sources, target)
    print(f"Создана база {written}: {game_count} партий из {len(sources)} файлов.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
