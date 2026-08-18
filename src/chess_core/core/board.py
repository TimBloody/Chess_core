"""Cell coordinates and m x n board geometry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Square:
    """Zero-based file (x) and rank (y) on an m x n board."""

    file: int
    rank: int

    def index(self, files: int) -> int:
        if files <= 0:
            raise ValueError("files must be positive")
        if not 0 <= self.file < files:
            raise ValueError("square file is outside board files")
        if self.rank < 0:
            raise ValueError("square rank must be non-negative")

        return self.rank * files + self.file

    @classmethod
    def from_index(cls, index: int, files: int, ranks: int) -> Square:
        if files <= 0:
            raise ValueError("files must be positive")
        if ranks <= 0:
            raise ValueError("ranks must be positive")
        if not 0 <= index < files * ranks:
            raise ValueError("index is outside board cells")

        return cls(file=index % files, rank=index // files)


@dataclass(frozen=True, slots=True)
class BoardShape:
    """Board dimensions: files (width) x ranks (height)."""

    files: int
    ranks: int

    def __post_init__(self) -> None:
        if self.files <= 0:
            raise ValueError("files must be positive")
        if self.ranks <= 0:
            raise ValueError("ranks must be positive")

    @property
    def cell_count(self) -> int:
        return self.files * self.ranks


class Board:
    """Logical board: shape, square validity, indexing."""

    def __init__(self, shape: BoardShape) -> None:
        self._shape = shape

    @property
    def shape(self) -> BoardShape:
        return self._shape

    def is_on_board(self, square: Square) -> bool:
        return (
            0 <= square.file < self._shape.files
            and 0 <= square.rank < self._shape.ranks
        )

    def all_squares_mask(self) -> int:
        """Bit mask of all valid cells for this shape."""
        return (1 << self._shape.cell_count) - 1
