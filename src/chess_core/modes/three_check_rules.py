"""Three-check state transition rules."""

from __future__ import annotations

from chess_core.core.move import Action
from chess_core.core.movegen import MoveGenerator
from chess_core.core.state import GameState


class ThreeCheckCounter:
    """Increment ``checks_given`` when an action leaves the opponent in check."""

    def apply_after_action(self, action: Action, state: object) -> object:
        if not isinstance(state, GameState):
            return state
        mode = state.extras.get("mode")
        if mode is None:
            return state
        opponent = state.side_to_move.opponent()
        if not MoveGenerator(mode).is_in_check(state, opponent):
            return state
        given = state.extras.setdefault("checks_given", {"white": 0, "black": 0})
        actor_key = state.side_to_move.name.lower()
        given[actor_key] = int(given.get(actor_key, 0)) + 1
        return state
