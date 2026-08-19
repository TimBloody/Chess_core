"""Helpers for locating UI SVG assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chess_core.infra.paths import assets_root as resolve_assets_root
from chess_core.ui.piece_assets import parse_display_key

DEFAULT_SHOGI_SET = "kanji_brown"
SHOGI_PIECE_SETS = {
    "kanji_brown": "Деревянные",
    "shogi_bnw": "Стилизованные",
}

_active_shogi_set = DEFAULT_SHOGI_SET


def shogi_piece_set() -> str:
    return _active_shogi_set


def set_shogi_piece_set(name: str) -> None:
    global _active_shogi_set
    if name not in SHOGI_PIECE_SETS:
        raise ValueError(f"Unknown shogi piece set: {name!r}")
    _active_shogi_set = name


@dataclass(frozen=True)
class AssetsLoader:
    """Resolve packaged project asset paths for PyQt renderers."""

    assets_root: Path | None = None

    def __post_init__(self) -> None:
        if self.assets_root is None:
            object.__setattr__(self, "assets_root", resolve_assets_root())

    @property
    def lichess_pieces_dir(self) -> Path:
        return self._required_dir("lichess", "pieces", "cburnett")

    @property
    def lichess_board_dir(self) -> Path:
        return self._required_dir("lichess", "board")

    @property
    def shogi_pieces_dir(self) -> Path:
        return self._required_dir("lishogi", "pieces", "standard", shogi_piece_set())

    @property
    def dobutsu_pieces_dir(self) -> Path:
        return self._required_dir("lishogi", "pieces", "dobutsu", "dobutsu")

    @property
    def light_square_path(self) -> Path:
        return self._required_file(self.lichess_board_dir / "light_square.svg")

    @property
    def dark_square_path(self) -> Path:
        return self._required_file(self.lichess_board_dir / "dark_square.svg")

    def chess_piece_path(self, piece_key: str) -> Path:
        return self._required_file(self.lichess_pieces_dir / f"{piece_key}.svg")

    def shogi_piece_path(self, piece_key: str) -> Path:
        path = self._shogi_file(piece_key)
        if path is None:
            raise FileNotFoundError(f"Asset file not found for shogi key: {piece_key!r}")
        return path

    def piece_path(self, piece_key: str) -> Path:
        """Return a matching chess or shogi SVG path for a piece key."""

        stem, _owner = parse_display_key(piece_key)
        if stem.startswith("dobutsu/"):
            filename = stem.split("/", 1)[1]
            return self._required_file(self.dobutsu_pieces_dir / f"{filename}.svg")

        chess_path = self.lichess_pieces_dir / f"{stem}.svg"
        if chess_path.is_file():
            return chess_path

        shogi_path = self._shogi_file(stem)
        if shogi_path is not None:
            return shogi_path

        variant_path = self.assets_root / "variants" / f"{stem}.svg"
        if variant_path.is_file():
            return variant_path

        checkers_path = self.assets_root / "checkers" / f"{stem}.svg"
        if checkers_path.is_file():
            return checkers_path

        boardgames_path = self.assets_root / "boardgames" / f"{stem}.svg"
        if boardgames_path.is_file():
            return boardgames_path

        raise FileNotFoundError(f"No SVG asset found for piece key: {piece_key!r}")

    def ui_icon_path(self, name: str) -> Path:
        return self._required_file(self.assets_root / "ui" / f"{name}.svg")

    def sounds_dir(self) -> Path:
        return self.assets_root / "sounds"

    def sound_path(self, filename: str) -> Path | None:
        path = self.sounds_dir() / filename
        return path if path.is_file() else None

    def _shogi_file(self, stem: str) -> Path | None:
        preferred = self.assets_root / "lishogi" / "pieces" / "standard" / shogi_piece_set() / f"{stem}.svg"
        if preferred.is_file():
            return preferred
        for fallback in SHOGI_PIECE_SETS:
            if fallback == shogi_piece_set():
                continue
            candidate = self.assets_root / "lishogi" / "pieces" / "standard" / fallback / f"{stem}.svg"
            if candidate.is_file():
                return candidate
        return None

    def _required_dir(self, *parts: str) -> Path:
        path = self.assets_root.joinpath(*parts)
        if not path.is_dir():
            raise FileNotFoundError(f"Asset directory not found: {path}")
        return path

    @staticmethod
    def _required_file(path: Path) -> Path:
        if not path.is_file():
            raise FileNotFoundError(f"Asset file not found: {path}")
        return path
