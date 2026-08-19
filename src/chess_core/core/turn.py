"""Turn scenario: how many actions and in what order per player turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from chess_core.core.move import Action, ActionKind, Turn
from chess_core.core.piece import PieceSide


class StepKind(Enum):
    MOVE_OR_CAPTURE = auto()
    MOVE_OR_DROP = auto()
    DROP = auto()
    PLACE = auto()
    PLACE_BLOCKER = auto()
    OPTIONAL_PASS = auto()


_ACTION_TO_STEP = {
    ActionKind.MOVE_PIECE: StepKind.MOVE_OR_CAPTURE,
    ActionKind.DROP_PIECE: StepKind.DROP,
    ActionKind.PLACE_PIECE: StepKind.PLACE,
    ActionKind.PLACE_BLOCKER: StepKind.PLACE_BLOCKER,
    ActionKind.PASS: StepKind.OPTIONAL_PASS,
}


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
        action_to_step = _ACTION_TO_STEP
        action_index = 0
        for step_index, step in enumerate(self._steps):
            if action_index >= len(turn.actions):
                return all(remaining.optional for remaining in self._steps[step_index:])
            actual = action_to_step.get(turn.actions[action_index].kind)
            if actual == step.kind or (
                step.kind is StepKind.MOVE_OR_DROP
                and actual in {StepKind.MOVE_OR_CAPTURE, StepKind.DROP, StepKind.PLACE}
            ):
                action_index += 1
            elif not step.optional:
                return False
        return action_index == len(turn.actions)

    def matches_prefix(self, turn: Turn) -> bool:
        """True when ``turn.actions`` match a (possibly incomplete) prefix of steps."""
        action_to_step = _ACTION_TO_STEP
        action_index = 0
        for step in self._steps:
            if action_index >= len(turn.actions):
                return True
            actual = action_to_step.get(turn.actions[action_index].kind)
            if actual == step.kind or (
                step.kind is StepKind.MOVE_OR_DROP
                and actual in {StepKind.MOVE_OR_CAPTURE, StepKind.DROP, StepKind.PLACE}
            ):
                action_index += 1
            elif not step.optional:
                return False
        return action_index == len(turn.actions)

    def remaining_steps(self, actions: list[Action]) -> tuple[TurnStep, ...]:
        """Steps not yet consumed by ``actions``."""
        action_to_step = _ACTION_TO_STEP
        action_index = 0
        start = 0
        for step_index, step in enumerate(self._steps):
            if action_index >= len(actions):
                return self._steps[step_index:]
            actual = action_to_step.get(actions[action_index].kind)
            if actual == step.kind or (
                step.kind is StepKind.MOVE_OR_DROP
                and actual in {StepKind.MOVE_OR_CAPTURE, StepKind.DROP, StepKind.PLACE}
            ):
                action_index += 1
                start = step_index + 1
            elif not step.optional:
                return self._steps[step_index:]
        return self._steps[start:]


class TurnPolicy(Protocol):
    """Dynamic per-position turn length (two-move, duck, classic)."""

    def scenario_for(self, state: object) -> TurnScenario:
        pass

    def should_end_turn(self, state: object, actions: list[Action]) -> bool:
        pass


@dataclass(frozen=True, slots=True)
class StaticTurnPolicy:
    """Fixed scenario: the turn ends when ``TurnScenario.validate_turn`` passes."""

    scenario: TurnScenario

    def scenario_for(self, state: object) -> TurnScenario:
        del state
        return self.scenario

    def should_end_turn(self, state: object, actions: list[Action]) -> bool:
        side = getattr(state, "side_to_move", None)
        if side is None:
            return False
        return self.scenario.validate_turn(Turn(side, list(actions)))


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
