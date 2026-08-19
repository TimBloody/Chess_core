"""Filesystem adapter for ChessBase-compatible PGN exports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from chess_core.infra.paths import output_dir

_RESULTS = frozenset({"1-0", "0-1", "1/2-1/2", "*"})
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class PgnMetadata:
    """Standard PGN tags understood by ChessBase when opening a PGN file."""

    event: str = "Chess Core"
    site: str = "?"
    played_on: str = field(
        default_factory=lambda: date.today().isoformat().replace("-", ".")
    )
    round: str = "?"
    white: str = "?"
    black: str = "?"
    result: str = "*"
    white_elo: str = ""
    black_elo: str = ""
    eco: str = ""
    opening: str = ""
    variation: str = ""
    annotator: str = ""
    event_date: str = ""
    source: str = "Chess Core"

    def __post_init__(self) -> None:
        if self.result not in _RESULTS:
            raise ValueError(f"unsupported PGN result: {self.result!r}")

    def headers(self) -> dict[str, str]:
        headers = {
            "Event": self.event or "?",
            "Site": self.site or "?",
            "Date": self.played_on or "????.??.??",
            "Round": self.round or "?",
            "White": self.white or "?",
            "Black": self.black or "?",
            "Result": self.result,
        }
        optional = {
            "WhiteElo": self.white_elo,
            "BlackElo": self.black_elo,
            "ECO": self.eco.upper(),
            "Opening": self.opening,
            "Variation": self.variation,
            "Annotator": self.annotator,
            "EventDate": self.event_date,
            "Source": self.source,
        }
        headers.update({key: value for key, value in optional.items() if value})
        return headers

    def suggested_filename(self) -> str:
        parts = (self.played_on, self.white, self.black, self.event)
        stem = "_".join(_filename_part(part) for part in parts if part and part != "?")
        return f"{stem or 'game'}.pgn"


class PgnStorage:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else output_dir()

    def save(self, pgn_text: str, filename: str | None = None) -> Path:
        if not pgn_text.strip():
            raise ValueError("cannot save an empty PGN")
        self.directory.mkdir(parents=True, exist_ok=True)
        requested = Path(filename or "game.pgn").name
        safe_name = _safe_filename(requested)
        target = _available_path(self.directory / safe_name)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(pgn_text.rstrip() + "\n", encoding="utf-8", newline="\n")
        temporary.replace(target)
        return target


def _filename_part(value: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", value.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned.strip(" ._")[:80]


def _safe_filename(value: str) -> str:
    path = Path(value)
    stem = _filename_part(path.stem) or "game"
    return f"{stem}{path.suffix if path.suffix.lower() == '.pgn' else '.pgn'}"


def _available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"cannot allocate a unique PGN filename in {path.parent}")
