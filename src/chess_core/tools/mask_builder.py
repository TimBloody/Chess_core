"""Build and cache bit masks and ray tables for topologies and board shapes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from chess_core.core.board import BoardShape
from chess_core.core.rays import RayBuilder, RayTable
from chess_core.core.topology import CylindricalFilesTopology, FlatTopology, Topology

DEFAULT_MASKS_DIR = Path(__file__).resolve().parents[1] / "data" / "masks"
EIGHT_DIRECTIONS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


class MaskBuilder:
    """Offline generator for per-square attack/move masks and ray tables."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir or DEFAULT_MASKS_DIR

    def build_for_topology(
        self,
        shape: BoardShape,
        topology: Topology,
        directions: tuple[tuple[int, int], ...],
    ) -> RayTable:
        return RayBuilder(shape, topology).build_all_directions(directions)

    def write_tables(self, mode_id: str, table: RayTable) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"{mode_id}.json"
        payload = {
            "mode_id": mode_id,
            "rays": [
                {
                    "origin_index": ray.origin_index,
                    "direction": list(ray.direction),
                    "mask": ray.mask,
                }
                for ray in table.rays()
            ],
        }
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return output_path

    def build_all_builtin(self) -> None:
        for mode_id in BUILTIN_MODES:
            self.build_mode(mode_id)

    def build_mode(self, mode_id: str) -> Path:
        shape = BoardShape(files=8, ranks=8)
        if mode_id == "flat_8x8":
            topology: Topology = FlatTopology(shape)
        elif mode_id == "cylinder_8x8":
            topology = CylindricalFilesTopology(shape)
        else:
            raise ValueError(f"unknown mask mode: {mode_id}")

        table = self.build_for_topology(shape, topology, EIGHT_DIRECTIONS)
        return self.write_tables(mode_id, table)


BUILTIN_MODES = ("flat_8x8", "cylinder_8x8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bit mask / ray tables")
    parser.add_argument("--mode", choices=(*BUILTIN_MODES, "all"), default="flat_8x8")
    parser.add_argument("--out", type=Path, default=DEFAULT_MASKS_DIR)
    args = parser.parse_args()
    builder = MaskBuilder(output_dir=args.out)
    if args.mode == "all":
        builder.build_all_builtin()
    else:
        builder.build_mode(args.mode)


if __name__ == "__main__":
    main()
