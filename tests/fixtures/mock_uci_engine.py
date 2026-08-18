"""Minimal mock UCI engine for tests."""

from __future__ import annotations

import sys


def main() -> int:
    for line in sys.stdin:
        command = line.strip()
        if command == "uci":
            print("id name MockEngine")
            print("uciok", flush=True)
        elif command == "isready":
            print("readyok", flush=True)
        elif command.startswith("go"):
            print("info score cp 25 depth 8 pv e2e4 e7e5", flush=True)
            print("bestmove e2e4", flush=True)
        elif command == "quit":
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
