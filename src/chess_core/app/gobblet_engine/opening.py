"""Opening book of best moves for canonical Gobblet keys."""

from __future__ import annotations

import struct
from collections import deque
from pathlib import Path

from chess_core.app.gobblet_engine.bits import NativeMove, apply_move, swap, terminal_value
from chess_core.app.gobblet_engine.canon import canonical, canonical_key, invert_perm, map_move
from chess_core.app.gobblet_engine.moves import legal_moves, move_size
from chess_core.app.gobblet_engine.search import MATE, TTEntry, _INF, search_best

MAGIC = b"GGOB01"
_RECORD = struct.Struct("<QbBh")


class GobbletOpeningBook:
    def __init__(self, entries: dict[int, tuple[NativeMove, int]] | None = None) -> None:
        self._entries = dict(entries or {})

    def probe(self, state: int) -> tuple[NativeMove | None, int]:
        oriented, perm = canonical(state)
        entry = self._entries.get(oriented)
        if entry is None:
            return None, 0
        move, score = entry
        return map_move(move, invert_perm(perm)), score

    def __len__(self) -> int:
        return len(self._entries)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(self._entries.items(), key=lambda item: item[0])
        with path.open("wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack("<I", len(items)))
            for key, (move, score) in items:
                handle.write(_RECORD.pack(key, move.start, move.end, score))

    @classmethod
    def load(cls, path: Path) -> GobbletOpeningBook:
        with path.open("rb") as handle:
            magic = handle.read(len(MAGIC))
            if magic != MAGIC:
                raise ValueError(f"not a gobblet opening book: {path}")
            count = struct.unpack("<I", handle.read(4))[0]
            entries: dict[int, tuple[NativeMove, int]] = {}
            for _ in range(count):
                key, start, end, score = _RECORD.unpack(handle.read(_RECORD.size))
                entries[int(key)] = (NativeMove(int(start), int(end)), int(score))
        return cls(entries)


def build_opening_book(*, max_ply: int = 5, leaf_depth: int = 1, progress=None) -> GobbletOpeningBook:
    """Unique canonical positions through `max_ply`, then negamax.

    Leaves (ply == max_ply, or terminals) are scored by `search_best`. Internal
    nodes take max of -child. Moves are stored in the parent's canonical frame.
    """
    children: dict[int, list[tuple[NativeMove, int]]] = {}
    min_ply: dict[int, int] = {0: 0}
    queue: deque[int] = deque([0])
    while queue:
        state = queue.popleft()
        ply = min_ply[state]
        if terminal_value(state) or ply >= max_ply:
            children[state] = []
            continue
        by_child: dict[int, NativeMove] = {}
        for move in legal_moves(state):
            raw = swap(apply_move(state, move, move_size(state, move)))
            child = canonical_key(raw)
            if child not in by_child:
                by_child[child] = move
            if child not in min_ply:
                min_ply[child] = ply + 1
                queue.append(child)
        children[state] = [(move, child) for child, move in by_child.items()]

    leaf_total = sum(
        1 for state, kids in children.items() if not kids and not terminal_value(state)
    )
    if progress is not None:
        progress(f"enumerated {len(children)} canonical positions, {leaf_total} leaves")

    values: dict[int, int] = {}
    best_moves: dict[int, NativeMove] = {}
    tt: dict[int, TTEntry] = {}
    scored = 0
    internals: list[tuple[int, list[tuple[NativeMove, int]]]] = []
    for state, kids in children.items():
        term = terminal_value(state)
        if term:
            values[state] = term * MATE
            continue
        if not kids:
            move, score = search_best(
                state, depth=leaf_depth, tt=tt, iterative=False, ordered=False, probe_win=True
            )
            values[state] = score
            if move is not None:
                best_moves[state] = move
            scored += 1
            if progress is not None and (scored == 1 or scored == leaf_total or scored % 10000 == 0):
                progress(f"scored {scored}/{leaf_total} leaves")
            continue
        internals.append((state, kids))

    if progress is not None:
        progress(f"backing up {len(internals)} internal positions")
    changed = True
    passes = 0
    while changed and passes < 32:
        changed = False
        passes += 1
        for state, kids in internals:
            best = -_INF
            best_move: NativeMove | None = None
            for move, child in kids:
                score = -values.get(child, 0)
                if score > best:
                    best = score
                    best_move = move
            if values.get(state) != best:
                values[state] = best
                if best_move is not None:
                    best_moves[state] = best_move
                changed = True

    return GobbletOpeningBook({key: (move, values[key]) for key, move in best_moves.items()})
