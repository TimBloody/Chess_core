"""Board connectivity: flat, cylindrical, portals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.bitboard import BitMask


class TopologyKind(Enum):
    FLAT = auto()
    CYLINDER_FILES = auto()
    PORTAL = auto()


@dataclass(frozen=True, slots=True)
class PortalLink:
    from_square: Square
    to_square: Square


class Topology(Protocol):
    def neighbors(self, square: Square) -> BitMask:
        pass

    def step(self, square: Square, direction: tuple[int, int]) -> Square | None:
        pass


class AdjacencyMap:
    """Precomputed neighbor masks per square for a topology."""

    def __init__(self, shape: BoardShape, topology: Topology) -> None:
        self._shape = shape
        self._neighbors = tuple(
            topology.neighbors(Square.from_index(index, shape.files, shape.ranks)).value
            for index in range(shape.cell_count)
        )

    def neighbors_of(self, square_index: int) -> int:
        if not 0 <= square_index < self._shape.cell_count:
            raise ValueError("square_index is outside board cells")

        return self._neighbors[square_index]


class FlatTopology:
    def __init__(self, shape: BoardShape) -> None:
        self._shape = shape
        self._board = Board(shape)

    def neighbors(self, square: Square) -> BitMask:
        mask = 0
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if df == 0 and dr == 0:
                    continue

                neighbor = self.step(square, (df, dr))
                if neighbor is not None:
                    mask |= 1 << neighbor.index(self._shape.files)

        return BitMask(mask)

    def step(self, square: Square, direction: tuple[int, int]) -> Square | None:
        df, dr = direction
        target = Square(file=square.file + df, rank=square.rank + dr)
        if not self._board.is_on_board(target):
            return None

        return target


class CylindricalFilesTopology:
    """Vertical edges glued: file 0 connects to file files-1."""

    def __init__(self, shape: BoardShape) -> None:
        self._shape = shape

    def neighbors(self, square: Square) -> BitMask:
        mask = 0
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if df == 0 and dr == 0:
                    continue

                neighbor = self.step(square, (df, dr))
                if neighbor is not None:
                    mask |= 1 << neighbor.index(self._shape.files)

        return BitMask(mask)

    def step(self, square: Square, direction: tuple[int, int]) -> Square | None:
        df, dr = direction
        target_rank = square.rank + dr
        if not 0 <= target_rank < self._shape.ranks:
            return None

        target_file = (square.file + df) % self._shape.files
        return Square(file=target_file, rank=target_rank)


class PortalTopology:
    def __init__(self, shape: BoardShape, links: tuple[PortalLink, ...]) -> None:
        self._shape = shape
        self._flat = FlatTopology(shape)
        board = Board(shape)
        for link in links:
            if not board.is_on_board(link.from_square) or not board.is_on_board(link.to_square):
                raise ValueError("portal endpoints must be on the board")
        if len({link.from_square for link in links}) != len(links):
            raise ValueError("portal sources must be unique")
        self._links = {link.from_square: link.to_square for link in links}

    def neighbors(self, square: Square) -> BitMask:
        mask = self._flat.neighbors(square).value
        portal_target = self._links.get(square)
        if portal_target is not None:
            mask |= 1 << portal_target.index(self._shape.files)

        return BitMask(mask)

    def step(self, square: Square, direction: tuple[int, int]) -> Square | None:
        target = self._flat.step(square, direction)
        if target is not None:
            return target

        return self._links.get(square)
