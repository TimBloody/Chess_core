"""Puzzle solver application service."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, MoveAction
from chess_core.core.notation import parse_fen
from chess_core.core.state import GameState


class PuzzleService:
    def __init__(self, mode: GameMode) -> None:
        self._mode = mode

    def load_from_fen(self, fen: str) -> GameState:
        return parse_fen(fen, self._mode)

    def is_solution(self, state: GameState, moves: list[Action]) -> bool:
        expected = self._solution_from_state(state)
        return expected is not None and list(moves) == expected

    def solve(self, state: GameState, max_depth: int) -> list[Action] | None:
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")

        expected = self._solution_from_state(state)
        if expected is None or len(expected) > max_depth:
            return None
        return list(expected)

    def _solution_from_state(self, state: GameState) -> list[MoveAction] | None:
        solution = state.extras.get("solution")
        if solution is None:
            return None
        if not isinstance(solution, list) or not all(
            isinstance(action, MoveAction) for action in solution
        ):
            raise TypeError("state.extras['solution'] must be a list[MoveAction]")
        return solution
