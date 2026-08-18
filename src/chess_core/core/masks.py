"""Loading generated ray tables and building finite leap masks."""

from __future__ import annotations

import json
from pathlib import Path

from chess_core.core.board import BoardShape, Square
from chess_core.core.rays import Ray, RayTable
from chess_core.core.topology import Topology


class MaskTableLoader:
    """Read the stable JSON format emitted by tools.mask_builder."""

    def load(self, path: Path) -> RayTable:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rays = [
            Ray(
                origin_index=int(record["origin_index"]),
                direction=tuple(record["direction"]),
                mask=int(record["mask"]),
            )
            for record in payload["rays"]
        ]
        table = RayTable()
        table.load(rays)
        return table


def leap_mask(
    origin: Square,
    offsets: tuple[tuple[int, int], ...],
    shape: BoardShape,
    topology: Topology,
) -> int:
    """Build an attack mask for a finite set of topology-aware offsets."""

    mask = 0
    for offset in offsets:
        target = topology.step(origin, offset)
        if target is not None:
            mask |= 1 << target.index(shape.files)
    return mask
