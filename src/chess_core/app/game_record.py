"""Game record: turn journal, timeline navigation, local undo."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.state import GameState


def position_snapshot(state: GameState) -> GameState:
    """Position-only clone without history (for replay and movegen probes)."""
    return state.clone(include_history=False)


def strip_history(state: GameState) -> GameState:
    """Return a position snapshot with empty history."""
    return position_snapshot(state)


@dataclass(frozen=True, slots=True)
class TurnRecord:
    turn: Turn
    revision: int
    notation: str = ""


@dataclass
class GameRecord:
    mode: GameMode
    initial: GameState
    turns: list[TurnRecord] = field(default_factory=list)
    live_revision: int = 0
    view_revision: int = 0
    _snapshots: list[GameState] = field(default_factory=list)

    @classmethod
    def from_mode(cls, mode: GameMode, initial: GameState | None = None) -> GameRecord:
        start = strip_history(initial or mode.initial_state())
        start.extras["mode"] = mode
        record = cls(mode=mode, initial=deepcopy(start))
        record._snapshots = [deepcopy(start)]
        return record

    @property
    def is_live(self) -> bool:
        return self.view_revision == self.live_revision

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def state_at(self, revision: int) -> GameState:
        if not 0 <= revision <= self.live_revision:
            raise ValueError(f"revision {revision} out of range 0..{self.live_revision}")
        if revision < len(self._snapshots):
            return self._snapshots[revision].clone(include_history=False)
        state = self.initial.clone(include_history=False)
        for index in range(revision):
            state = state.apply_turn(self.turns[index].turn, record_history=False)
        return state

    def current_view_state(self) -> GameState:
        return self.state_at(self.view_revision)

    def live_state(self) -> GameState:
        return self.state_at(self.live_revision)

    def go_to(self, revision: int) -> GameState:
        self.view_revision = revision
        return self.current_view_state()

    def go_live(self) -> GameState:
        self.view_revision = self.live_revision
        return self.live_state()

    def append_turn(
        self,
        turn: Turn,
        *,
        notation: str = "",
    ) -> GameState:
        if not self.is_live:
            raise RuntimeError("cannot play while viewing history; call go_live() first")
        if self.view_revision < len(self.turns):
            self.turns = self.turns[: self.view_revision]
            self._snapshots = self._snapshots[: self.view_revision + 1]

        prev = self.live_state()
        next_state = prev.apply_turn(turn, record_history=True)
        self.live_revision += 1
        self.view_revision = self.live_revision
        self.turns.append(
            TurnRecord(
                turn=turn,
                revision=self.live_revision,
                notation=notation,
            )
        )
        self._snapshots.append(next_state.clone(include_history=False))
        return next_state

    def undo_last_turn(self) -> GameState:
        if self.live_revision == 0:
            raise RuntimeError("no turns to undo")
        self.turns.pop()
        self._snapshots.pop()
        self.live_revision -= 1
        self.view_revision = self.live_revision
        return self.live_state()

    def reset(self, initial: GameState | None = None) -> GameState:
        start = strip_history(initial or self.mode.initial_state())
        start.extras["mode"] = self.mode
        self.initial = deepcopy(start)
        self.turns.clear()
        self._snapshots = [deepcopy(start)]
        self.live_revision = 0
        self.view_revision = 0
        return self.live_state()

    def move_log(self, *, paired: bool = True) -> list[str]:
        if not paired:
            return [entry.notation for entry in self.turns if entry.notation]
        lines: list[str] = []
        move_number = 1
        index = 0
        while index < len(self.turns):
            white_text = ""
            black_text = ""
            if self.turns[index].turn.side.name == "WHITE":
                white_text = self.turns[index].notation
                index += 1
                if index < len(self.turns) and self.turns[index].turn.side.name == "BLACK":
                    black_text = self.turns[index].notation
                    index += 1
            else:
                black_text = self.turns[index].notation
                index += 1
            if black_text:
                lines.append(f"{move_number}. {white_text}  {black_text}".strip())
            elif white_text:
                lines.append(f"{move_number}. {white_text}")
            move_number += 1
        return lines
