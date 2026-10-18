"""Read/write PGN databases in the encoding ChessBase 16 expects.

ChessBase 16 opens a multi-game ``.pgn`` as a PGN database. On Windows it
detects UTF-8 reliably when the file has a BOM, and it is happiest with CRLF
line endings and a complete Seven Tag Roster (filled in ``core.pgn``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from chess_core.core.pgn import PgnGame, parse_pgn
from chess_core.infra.paths import project_root

GAME_FILE_SUFFIXES: frozenset[str] = frozenset({".pgn", ".txt"})
UTF8_BOM = b"\xef\xbb\xbf"


def default_games_dir() -> Path:
    env = os.environ.get("CHESS_CORE_GAMES_DIR")
    if env:
        return Path(env)
    local = project_root() / "games"
    if local.is_dir():
        return local
    return Path.home()


def discover_game_files(
    folder: Path,
    *,
    recursive: bool = False,
    exclude: Path | None = None,
) -> tuple[Path, ...]:
    if not folder.is_dir():
        raise FileNotFoundError(f"folder does not exist: {folder}")
    excluded = exclude.resolve() if exclude is not None else None
    iterator: Iterator[Path]
    if recursive:
        iterator = (path for path in folder.rglob("*") if path.is_file())
    else:
        iterator = (path for path in folder.iterdir() if path.is_file())
    found: list[Path] = []
    for path in iterator:
        if path.suffix.lower() not in GAME_FILE_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        if excluded is not None and path.resolve() == excluded:
            continue
        found.append(path)
    found.sort(key=lambda item: str(item).lower())
    return tuple(found)


def read_pgn_text(path: Path) -> str:
    return decode_pgn_bytes(path.read_bytes())


def decode_pgn_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be")
    if data.startswith(UTF8_BOM):
        return data.decode("utf-8-sig")
    for encoding in ("utf-8", "cp1251", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def encode_chessbase_pgn(text: str) -> bytes:
    """UTF-8 with BOM and CRLF — ChessBase 16 PGN database on Windows."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    body = normalized.replace("\n", "\r\n")
    if body and not body.endswith("\r\n"):
        body += "\r\n"
    return body.encode("utf-8-sig")


def write_chessbase_pgn(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_chessbase_pgn(text))


def load_pgn_games(path: Path) -> tuple[PgnGame, ...]:
    return parse_pgn(read_pgn_text(path))


def load_folder_texts(
    folder: Path,
    *,
    recursive: bool = False,
    exclude: Path | None = None,
) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for path in discover_game_files(folder, recursive=recursive, exclude=exclude):
        try:
            text = read_pgn_text(path)
        except OSError:
            continue
        try:
            label = str(path.relative_to(folder))
        except ValueError:
            label = path.name
        items.append((label, text))
    return tuple(items)
