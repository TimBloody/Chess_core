"""Turn scenario: how many actions and in what order per player turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from chess_core.core.move import ActionKind, Turn
from chess_core.core.piece import PieceSide


class StepKind(Enum):
    MOVE_OR_CAPTURE = auto()
    MOVE_OR_DROP = auto()
    DROP = auto()
    PLACE_BLOCKER = auto()
    OPTIONAL_PASS = auto()


@dataclass(frozen=True, slots=True)
class TurnStep:
    """One required or optional step in a turn scenario."""

    kind: StepKind
    optional: bool = False
    label: str = ""


class TurnScenario:
    """Defines multi-action turns (duck chess, two-move chess, etc.)."""

    def __init__(self, steps: tuple[TurnStep, ...]) -> None:
        self._steps = steps

    @property
    def steps(self) -> tuple[TurnStep, ...]:
        return self._steps

    def required_action_count(self) -> int:
        return sum(not step.optional for step in self._steps)

    def validate_turn(self, turn: Turn) -> bool:
        if not self.required_action_count() <= len(turn.actions) <= len(self._steps):
            return False
        action_to_step = {
            ActionKind.MOVE_PIECE: StepKind.MOVE_OR_CAPTURE,
            ActionKind.DROP_PIECE: StepKind.DROP,
            ActionKind.PLACE_BLOCKER: StepKind.PLACE_BLOCKER,
            ActionKind.PASS: StepKind.OPTIONAL_PASS,
        }
        action_index = 0
        for step_index, step in enumerate(self._steps):
            if action_index >= len(turn.actions):
                return all(remaining.optional for remaining in self._steps[step_index:])
            actual = action_to_step.get(turn.actions[action_index].kind)
            if actual == step.kind or (
                step.kind is StepKind.MOVE_OR_DROP
                and actual in {StepKind.MOVE_OR_CAPTURE, StepKind.DROP}
            ):
                action_index += 1
            elif not step.optional:
                return False
        return action_index == len(turn.actions)


class TurnOrder(Protocol):
    def next_side(self, current: PieceSide) -> PieceSide:
        pass


@dataclass(frozen=True, slots=True)
class AlternatingSides:
    sides: tuple[PieceSide, ...]

    def next_side(self, current: PieceSide) -> PieceSide:
        if current not in self.sides:
            raise ValueError(f"unknown side in turn order: {current}")
        index = self.sides.index(current)
        return self.sides[(index + 1) % len(self.sides)]
