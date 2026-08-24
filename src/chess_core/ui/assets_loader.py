"""Helpers for locating UI SVG assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chess_core.infra.paths import assets_root as resolve_assets_root
from chess_core.ui.piece_keys import parse_display_key


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
        return self._required_dir("lishogi", "pieces", "standard", "shogi_bnw")

    @property
    def dobutsu_pieces_dir(self) -> Path:
        return self._required_dir("lishogi", "pieces", "dobutsu")

    @property
    def light_square_path(self) -> Path:
        return self._required_file(self.lichess_board_dir / "light_square.svg")

    @property
    def dark_square_path(self) -> Path:
        return self._required_file(self.lichess_board_dir / "dark_square.svg")

    def chess_piece_path(self, piece_key: str) -> Path:
        return self._required_file(self.lichess_pieces_dir / f"{piece_key}.svg")

    def shogi_piece_path(self, piece_key: str) -> Path:
        return self._required_file(self.shogi_pieces_dir / f"{piece_key}.svg")

    def dobutsu_piece_path(self, piece_key: str) -> Path:
        return self._required_file(self.dobutsu_pieces_dir / f"{piece_key}.svg")

    def piece_path(self, piece_key: str) -> Path:
        """Return a matching chess, shogi, or dobutsu SVG path for a piece key."""

        stem, _owner = parse_display_key(piece_key)
        if stem.startswith("dobutsu/"):
            filename = stem.split("/", 1)[1]
            return self.dobutsu_piece_path(filename)

        chess_path = self.lichess_pieces_dir / f"{stem}.svg"
        if chess_path.is_file():
            return chess_path

        shogi_path = self.shogi_pieces_dir / f"{stem}.svg"
        if shogi_path.is_file():
            return shogi_path

        raise FileNotFoundError(f"No SVG asset found for piece key: {piece_key!r}")

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
