"""On-disk WDL tablebase for stm-relative 54-bit Gobblet keys."""

from __future__ import annotations

import struct
from collections import deque
from pathlib import Path

from chess_core.app.gobblet_engine.bits import apply_move, swap, terminal_value
from chess_core.app.gobblet_engine.canon import canonical_key
from chess_core.app.gobblet_engine.moves import legal_moves, move_size

MAGIC = b"GGTB01"
_RECORD = struct.Struct("<Qb")


class GobbletTablebase:
    def __init__(self, wdl: dict[int, int] | None = None) -> None:
        self._wdl = dict(wdl or {})

    def get(self, state: int) -> int | None:
        value = self._wdl.get(canonical_key(state))
        if value in (-1, 0, 1):
            return value
        return None

    def __len__(self) -> int:
        return len(self._wdl)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(self._wdl.items())
        with path.open("wb") as handle:
            handle.write(MAGIC)
            handle.write(struct.pack("<I", len(items)))
            for key, value in items:
                handle.write(_RECORD.pack(key, value))

    @classmethod
    def load(cls, path: Path) -> GobbletTablebase:
        with path.open("rb") as handle:
            magic = handle.read(len(MAGIC))
            if magic != MAGIC:
                raise ValueError(f"not a gobblet tablebase: {path}")
            count = struct.unpack("<I", handle.read(4))[0]
            wdl: dict[int, int] = {}
            for _ in range(count):
                key, value = _RECORD.unpack(handle.read(_RECORD.size))
                wdl[key] = int(value)
        return cls(wdl)


def build_proved_tablebase(*, max_nodes: int = 8_000) -> GobbletTablebase:
    """BFS from the empty board, then retrograde on the visited graph.

    Only proved wins/losses/draws are stored. Frontier nodes with unexpanded
    children stay unknown so the engine can fall back to 5-ply search.
    """
    children: dict[int, list[int]] = {}
    visited: set[int] = {0}
    queue: deque[int] = deque([0])
    while queue and len(visited) < max_nodes:
        state = queue.popleft()
        if terminal_value(state):
            children[state] = []
            continue
        next_states: list[int] = []
        for move in legal_moves(state):
            child = canonical_key(swap(apply_move(state, move, move_size(state, move))))
            next_states.append(child)
            if child not in visited:
                visited.add(child)
                queue.append(child)
        children[state] = next_states
    for state in list(visited):
        children.setdefault(state, [])

    wdl: dict[int, int] = {}
    for state in children:
        term = terminal_value(state)
        if term:
            wdl[state] = term

    changed = True
    while changed:
        changed = False
        for state, next_states in children.items():
            if state in wdl:
                continue
            if terminal_value(state):
                continue
            if not next_states:
                wdl[state] = 0
                changed = True
                continue
            known = [wdl.get(child) for child in next_states]
            if any(value == -1 for value in known if value is not None):
                wdl[state] = 1
                changed = True
                continue
            if any(value is None for value in known):
                continue
            if all(value == 1 for value in known):
                wdl[state] = -1
            else:
                wdl[state] = 0
            changed = True
    return GobbletTablebase(wdl)
