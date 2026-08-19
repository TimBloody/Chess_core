"""Two-move chess turn policy."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.move import Action
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind, TurnScenario, TurnStep


def _move_step_kind(state: GameState) -> StepKind:
    mode = state.extras.get("mode")
    if mode is not None and mode.drop_rule is not None:
        return StepKind.MOVE_OR_DROP
    return StepKind.MOVE_OR_CAPTURE


def _committed_turns(state: GameState) -> int:
    if state.history.metadata:
        return len(state.history.metadata)
    return int(state.extras.get("committed_turns", 0))


@dataclass(frozen=True, slots=True)
class DoubleMoveTurnPolicy:
    """White's first turn is one move; in-check turns are one move; otherwise two."""

    def scenario_for(self, state: object) -> TurnScenario:
        if not isinstance(state, GameState):
            raise TypeError("state must be GameState")
        move_kind = _move_step_kind(state)
        if _committed_turns(state) == 0 and state.side_to_move is PieceSide.WHITE:
            return TurnScenario((TurnStep(move_kind),))
        mode = state.extras.get("mode")
        if mode is not None and MoveGenerator(mode).is_in_check(state):
            return TurnScenario((TurnStep(move_kind),))
        return TurnScenario(
            (
                TurnStep(move_kind, label="move 1"),
                TurnStep(move_kind, label="move 2"),
            )
        )

    def should_end_turn(self, state: object, actions: list[Action]) -> bool:
        if not isinstance(state, GameState):
            raise TypeError("state must be GameState")
        if len(actions) >= 2:
            return True
        if len(actions) < 1:
            return False
        mode = state.extras.get("mode")
        if mode is None:
            return False
        actor = state.side_to_move
        return MoveGenerator(mode).is_in_check(state, actor.opponent())
