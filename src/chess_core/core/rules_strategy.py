"""Pluggable rules strategy with a default chess-like adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chess_core.core.board import Square
from chess_core.core.move import (
    Action,
    DropAction,
    MoveAction,
    PassAction,
    PlaceAction,
    PlaceBlockerAction,
    Turn,
)
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.outcome import GameOutcome, OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.state import GameState
from chess_core.core.turn import StepKind

if TYPE_CHECKING:
    from chess_core.core.gamemode import GameMode


class RulesStrategy(Protocol):
    def legal_turns(self, state: GameState) -> list[Turn]:
        ...

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        ...

    def outcome(self, state: GameState) -> GameOutcome:
        ...

    def format_turn(
        self,
        turn: Turn,
        *,
        before: GameState,
        after: GameState,
        style: NotationStyle = NotationStyle.FROM_TO,
    ) -> str:
        ...


class DefaultRulesStrategy:
    """Adapter over GameState.apply_turn and MoveGenerator for chess-like modes."""

    def __init__(self, mode: GameMode) -> None:
        self._mode = mode
        self._generator = MoveGenerator(mode)

    def legal_turns(self, state: GameState) -> list[Turn]:
        return _compose_legal_turns(self._mode, state, self._generator)

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        return state.apply_turn(turn, record_history=record_history)

    def outcome(self, state: GameState) -> GameOutcome:
        if self._uses_victory(VictoryKind.MATERIAL):
            if not self._generator.has_any_legal(state):
                return GameOutcome(
                    status=OutcomeStatus.WIN,
                    winner=_opponent(state.side_to_move, self._mode),
                    reason="no_legal_moves",
                )
            return GameOutcome(status=OutcomeStatus.ACTIVE)
        if self._generator.is_checkmate(state):
            winner = _opponent(state.side_to_move, self._mode)
            return GameOutcome(
                status=OutcomeStatus.WIN,
                winner=winner,
                reason="checkmate",
            )
        if self._generator.is_stalemate(state):
            return GameOutcome(status=OutcomeStatus.DRAW, reason="stalemate")
        if self._uses_victory(VictoryKind.CHECKMATE) and self._generator.is_in_check(state):
            return GameOutcome(status=OutcomeStatus.ACTIVE, reason="check")
        return GameOutcome(status=OutcomeStatus.ACTIVE)

    def format_turn(
        self,
        turn: Turn,
        *,
        before: GameState,
        after: GameState,
        style: NotationStyle = NotationStyle.FROM_TO,
    ) -> str:
        return format_turn(turn, before=before, after=after, style=style)

    def _uses_victory(self, kind: VictoryKind) -> bool:
        conditions = (
            self._mode.victory
            if isinstance(self._mode.victory, tuple)
            else (self._mode.victory,)
        )
        return any(
            isinstance(condition, VictoryCondition) and condition.kind is kind
            for condition in conditions
        )


def _opponent(side: PieceSide, mode: GameMode) -> PieceSide:
    return mode.turn_order.next_side(side)


def _compose_legal_turns(
    mode: GameMode, state: GameState, generator: MoveGenerator
) -> list[Turn]:
    steps = mode.turn_scenario.steps
    if not steps:
        return [
            Turn(state.side_to_move, [action])
            for action in generator.generate_legal(state)
        ]
    return _expand_turn_prefix(mode, state, generator, steps, (), 0)


def _expand_turn_prefix(
    mode: GameMode,
    state: GameState,
    generator: MoveGenerator,
    steps: tuple[object, ...],
    prefix: tuple[Action, ...],
    step_index: int,
) -> list[Turn]:
    side = state.side_to_move

    if step_index >= len(steps):
        if not prefix:
            return []
        turn = Turn(side, list(prefix))
        if _turn_is_legal(state, turn):
            return [turn]
        return []

    step = steps[step_index]
    probe_state = _probe_after_actions(state, prefix) if prefix else state
    candidates = _actions_for_step(generator, probe_state, step)

    turns: list[Turn] = []
    for action in candidates:
        turns.extend(
            _expand_turn_prefix(
                mode,
                state,
                generator,
                steps,
                prefix + (action,),
                step_index + 1,
            )
        )

    if getattr(step, "optional", False):
        turns.extend(
            _expand_turn_prefix(
                mode, state, generator, steps, prefix, step_index + 1
            )
        )
    return turns


def _turn_is_legal(state: GameState, turn: Turn) -> bool:
    try:
        state.apply_turn(turn, record_history=False)
    except (TypeError, ValueError):
        return False
    return True


def _probe_after_actions(state: GameState, actions: tuple[Action, ...]) -> GameState:
    if not actions:
        return state
    turn = Turn(state.side_to_move, list(actions))
    return state.apply_turn(
        turn,
        record_history=False,
        validate_scenario=False,
        switch_side=False,
    )


def _actions_for_step(
    generator: MoveGenerator, state: GameState, step: object
) -> list[Action]:
    kind = getattr(step, "kind", None)
    legal = generator.generate_legal(state)
    if kind is StepKind.MOVE_OR_CAPTURE:
        return [action for action in legal if isinstance(action, MoveAction)]
    if kind is StepKind.MOVE_OR_DROP:
        return [
            action
            for action in legal
            if isinstance(action, (MoveAction, DropAction))
        ]
    if kind is StepKind.DROP:
        return [action for action in legal if isinstance(action, DropAction)]
    if kind is StepKind.PLACE:
        return [action for action in legal if isinstance(action, PlaceAction)]
    if kind is StepKind.PLACE_BLOCKER:
        return _empty_square_blockers(state)
    if kind is StepKind.OPTIONAL_PASS:
        return [PassAction()]
    return list(legal)


def _empty_square_blockers(state: GameState) -> list[PlaceBlockerAction]:
    shape = state.board_state.board.shape
    actions: list[PlaceBlockerAction] = []
    for index in range(shape.cell_count):
        if state.board_state.piece_at(index) is None:
            actions.append(
                PlaceBlockerAction(
                    Square.from_index(index, shape.files, shape.ranks)
                )
            )
    return actions


def apply_place_action(state: GameState, turn: Turn, action: PlaceAction) -> None:
    """Apply a generic piece placement (shared by state and custom strategies)."""
    shape = state.board_state.board.shape
    target = action.to_square.index(shape.files)
    if state.board_state.piece_at(target) is not None:
        raise ValueError("cannot place onto an occupied square")
    state.board_state.cells[target] = Piece(action.piece_type, turn.side)
