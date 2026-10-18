"""Build a Gobblet opening book of the first few canonical plies.

D4 reflections/rotations collapse equivalent boards (empty cells toward c3).
Default is 5 unique half-moves from the empty board.

  python -m chess_core.tools.gobblet_opening
  python -m chess_core.tools.gobblet_opening --plies 5 --leaf-depth 1
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from chess_core.app.gobblet_engine.engine import packaged_opening_path
from chess_core.app.gobblet_engine.opening import build_opening_book
from chess_core.infra.paths import project_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plies", type=int, default=5, help="unique canonical plies from the empty board")
    parser.add_argument("--leaf-depth", type=int, default=1, help="heuristic search depth at book leaves")
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()
    started = time.monotonic()
    book = build_opening_book(
        max_ply=args.plies,
        leaf_depth=args.leaf_depth,
        progress=lambda message: print(message, flush=True),
    )
    elapsed = time.monotonic() - started
    service = Path(args.out) if args.out else project_root() / "data" / "gobblet" / "opening.ggb"
    book.save(service)
    packaged = packaged_opening_path()
    if service.resolve() != packaged.resolve():
        book.save(packaged)
        print(f"wrote {len(book)} canonical positions to {service} and {packaged} in {elapsed:.1f}s")
    else:
        print(f"wrote {len(book)} canonical positions to {service} in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
