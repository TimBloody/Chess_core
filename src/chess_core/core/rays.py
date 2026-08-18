"""Movement rays on empty board for a given topology."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.board import BoardShape, Square
from chess_core.core.topology import Topology


@dataclass(frozen=True, slots=True)
class Ray:
    """Cells reachable along one direction from origin until blocked by topology."""

    origin_index: int
    direction: tuple[int, int]
    mask: int


class RayTable:
    """Cached rays per (square, direction) for a topology."""

    def __init__(self) -> None:
        self._rays: dict[tuple[int, tuple[int, int]], int] = {}
        self._records: tuple[Ray, ...] = ()

    def ray_mask(self, origin_index: int, direction: tuple[int, int]) -> int:
        return self._rays[(origin_index, direction)]

    def load(self, rays: list[Ray]) -> None:
        self._records = tuple(rays)
        self._rays = {
            (ray.origin_index, ray.direction): ray.mask
            for ray in self._records
        }

    def rays(self) -> tuple[Ray, ...]:
        return self._records


class RayBuilder:
    """Build ray tables from BoardShape + Topology."""

    def __init__(self, shape: BoardShape, topology: Topology) -> None:
        self._shape = shape
        self._topology = topology

    def build_all_directions(self, directions: tuple[tuple[int, int], ...]) -> RayTable:
        rays = [
            self.build_line(
                Square.from_index(origin_index, self._shape.files, self._shape.ranks),
                direction,
            )
            for origin_index in range(self._shape.cell_count)
            for direction in directions
        ]
        table = RayTable()
        table.load(rays)
        return table

    def build_line(self, origin: Square, direction: tuple[int, int]) -> Ray:
        if direction == (0, 0):
            raise ValueError("direction must not be zero")

        origin_index = origin.index(self._shape.files)
        current = origin
        visited = {origin_index}
        mask = 0

        while True:
            next_square = self._topology.step(current, direction)
            if next_square is None:
                break

            next_index = next_square.index(self._shape.files)
            if next_index in visited:
                break

            visited.add(next_index)
            mask |= 1 << next_index
            current = next_square

        return Ray(origin_index=origin_index, direction=direction, mask=mask)
