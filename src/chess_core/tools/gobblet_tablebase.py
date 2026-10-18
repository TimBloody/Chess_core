"""Build a Gobblet WDL tablebase from proved retrograde labels.

Full-with-moves solve is hundreds of millions of positions (see possiblywrong /
brianhliou). This writes only positions proved on a bounded BFS from the start
(after D4 canonicalization). The engine probes the file and otherwise searches
5 plies. For the debut, use `python -m chess_core.tools.gobblet_opening`.

  python -m chess_core.tools.gobblet_tablebase --max-nodes 8000
"""

from __future__ import annotations

import argparse
from pathlib import Path

from chess_core.app.gobblet_engine import build_proved_tablebase, tablebase_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-nodes", type=int, default=8_000)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()
    table = build_proved_tablebase(max_nodes=args.max_nodes)
    path = Path(args.out) if args.out else tablebase_path()
    table.save(path)
    print(f"wrote {len(table)} proved positions to {path}")


if __name__ == "__main__":
    main()
