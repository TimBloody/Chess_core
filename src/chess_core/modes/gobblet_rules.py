"""Rules strategy for Gobblet Gobblers on a 3x3 board."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceAction, Turn
from chess_core.core.notation import NotationStyle, format_turn
from chess_core.core.outcome import GameOutcome, OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState

GOBBLET_SMALL = PieceTypeId("gobblet_small")
GOBBLET_MEDIUM = PieceTypeId("gobblet_medium")
GOBBLET_LARGE = PieceTypeId("gobblet_large")

GOBBLET_TYPES = (GOBBLET_SMALL, GOBBLET_MEDIUM, GOBBLET_LARGE)
GOBBLET_SIZES = {
    GOBBLET_SMALL: 1,
    GOBBLET_MEDIUM: 2,
    GOBBLET_LARGE: 3,
}


@dataclass(frozen=True, slots=True)
class GobbletOptions:
    """Place-only by default; relocate allows moving a visible gobblet."""

    allow_board_moves: bool = False


LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class GobbletRulesStrategy:
    """Stack-based gobble moves, reserve placements, reveal hail-mary."""

    def __init__(self, options: GobbletOptions | None = None) -> None:
        self._options = options or GobbletOptions()

    def legal_turns(self, state: GameState) -> list[Turn]:
        if self.outcome(state).is_finished:
            return []
        side = state.side_to_move
        turns: list[Turn] = []
        turns.extend(self._legal_places(state, side))
        if self._options.allow_board_moves:
            turns.extend(self._legal_moves(state, side))
        return turns

    def apply_turn(
        self, state: GameState, turn: Turn, *, record_history: bool = True
    ) -> GameState:
        if turn.side is not state.side_to_move:
            raise ValueError("turn side does not match side_to_move")
        if not turn.actions:
            raise ValueError("turn must contain at least one action")

        mode = state.extras.get("mode")
        if mode is not None and not mode.turn_scenario.validate_turn(turn):
            raise ValueError("turn does not match the game mode turn scenario")

        result = state.clone(include_history=record_history)
        turn_actions = []
        opponent = _opponent_side(turn.side, mode)

        for action in turn.actions:
            if isinstance(action, PlaceAction):
                _apply_place(result, turn, action)
            elif isinstance(action, MoveAction):
                if not self._options.allow_board_moves:
                    raise ValueError("board moves are disabled")
                revealed_lines = _apply_move(result, turn, action)
                files = result.board_state.board.shape.files
                if revealed_lines and (
                    not _hail_mary_blocks(action, revealed_lines, files)
                    or _has_three_in_a_row(result, opponent)
                ):
                    return _finish_turn(
                        result,
                        turn,
                        turn_actions + [action],
                        record_history,
                        GameOutcome(
                            status=OutcomeStatus.WIN,
                            winner=opponent,
                            reason="revealed-three-in-a-row",
                        ),
                        mode,
                    )
            else:
                raise TypeError(f"unsupported action: {type(action).__name__}")
            turn_actions.append(action)

        outcome = self.outcome(result)
        if outcome.is_finished:
            return _finish_turn(
                result, turn, turn_actions, record_history, outcome, mode
            )

        if record_history:
            result.history.actions.extend(turn_actions)
            result.history.metadata.append({"turn_side": turn.side.name})
        result.side_to_move = _next_side(result.side_to_move, mode)
        return result

    def outcome(self, state: GameState) -> GameOutcome:
        for side in (PieceSide.WHITE, PieceSide.BLACK):
            if _has_three_in_a_row(state, side):
                return GameOutcome(
                    status=OutcomeStatus.WIN,
                    winner=side,
                    reason="three-in-a-row",
                )
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

    def _legal_places(self, state: GameState, side: PieceSide) -> list[Turn]:
        reserve = state.extras.get("reserve", {}).get(side, {})
        shape = state.board_state.board.shape
        turns: list[Turn] = []
        for piece_type in GOBBLET_TYPES:
            if reserve.get(piece_type, 0) <= 0:
                continue
            piece = Piece(piece_type, side)
            for index in range(shape.cell_count):
                if _can_land(piece, index, state):
                    square = Square.from_index(index, shape.files, shape.ranks)
                    turns.append(Turn(side, [PlaceAction(piece_type, square)]))
        return turns

    def _legal_moves(self, state: GameState, side: PieceSide) -> list[Turn]:
        shape = state.board_state.board.shape
        files = shape.files
        opponent = _opponent_side(side, state.extras.get("mode"))
        turns: list[Turn] = []

        for from_index, piece in state.board_state.cells.items():
            if piece is None or piece.side is not side:
                continue
            from_square = Square.from_index(from_index, files, shape.ranks)
            lifted = _lift_probe(state, from_index)
            opp_lines = _winning_lines(lifted, opponent)
            if opp_lines:
                destinations = _hail_mary_destinations(
                    from_index, piece, opp_lines, lifted
                )
                if not destinations:
                    continue
                for to_index in sorted(destinations):
                    to_square = Square.from_index(to_index, files, shape.ranks)
                    turns.append(Turn(side, [MoveAction(from_square, to_square)]))
                continue

            for to_index in range(shape.cell_count):
                if to_index == from_index:
                    continue
                if _can_land(piece, to_index, lifted):
                    to_square = Square.from_index(to_index, files, shape.ranks)
                    turns.append(Turn(side, [MoveAction(from_square, to_square)]))
        return turns


def initial_reserve() -> dict[PieceSide, dict[PieceTypeId, int]]:
    counts = {piece_type: 2 for piece_type in GOBBLET_TYPES}
    return {
        PieceSide.WHITE: dict(counts),
        PieceSide.BLACK: dict(counts),
    }


def _finish_turn(
    result: GameState,
    turn: Turn,
    turn_actions: list[object],
    record_history: bool,
    outcome: GameOutcome,
    mode: object | None,
) -> GameState:
    if record_history:
        result.history.actions.extend(turn_actions)
        result.history.metadata.append(
            {"turn_side": turn.side.name, "outcome": outcome.reason}
        )
    if not outcome.is_finished:
        result.side_to_move = _next_side(result.side_to_move, mode)
    result.extras["outcome"] = outcome
    return result


def _next_side(current: PieceSide, mode: object | None) -> PieceSide:
    if mode is not None:
        return mode.turn_order.next_side(current)
    return (
        PieceSide.BLACK if current is PieceSide.WHITE else PieceSide.WHITE
    )


def _opponent_side(side: PieceSide, mode: object | None) -> PieceSide:
    return _next_side(side, mode)


def _piece_size(piece_type: PieceTypeId) -> int:
    try:
        return GOBBLET_SIZES[piece_type]
    except KeyError as exc:
        raise ValueError(f"unknown gobblet type: {piece_type.name}") from exc


def _stacks(state: GameState) -> dict[int, list[Piece]]:
    stacks = state.extras.setdefault("stacks", {})
    if not isinstance(stacks, dict):
        raise TypeError("extras['stacks'] must be a dict")
    return stacks


def _stack(state: GameState, index: int) -> list[Piece]:
    stacks = _stacks(state)
    if index not in stacks:
        occupant = state.board_state.piece_at(index)
        stacks[index] = [deepcopy(occupant)] if occupant is not None else []
    return stacks[index]


def _sync_cell(state: GameState, index: int) -> None:
    stack = _stack(state, index)
    state.board_state.cells[index] = deepcopy(stack[-1]) if stack else None


def _can_land(piece: Piece, target_index: int, state: GameState) -> bool:
    stack = _stack(state, target_index)
    if not stack:
        return True
    return _piece_size(piece.piece_type) > _piece_size(stack[-1].piece_type)


def _apply_place(state: GameState, turn: Turn, action: PlaceAction) -> None:
    reserve = state.extras.setdefault("reserve", initial_reserve())
    side_reserve = reserve.setdefault(turn.side, {})
    available = side_reserve.get(action.piece_type, 0)
    if available <= 0:
        raise ValueError("no pieces of that type in reserve")

    shape = state.board_state.board.shape
    target = action.to_square.index(shape.files)
    piece = Piece(action.piece_type, turn.side)
    if not _can_land(piece, target, state):
        raise ValueError("cannot place onto this square")

    side_reserve[action.piece_type] = available - 1
    _stack(state, target).append(piece)
    _sync_cell(state, target)


def _apply_move(
    state: GameState, turn: Turn, action: MoveAction
) -> tuple[tuple[int, ...], ...]:
    shape = state.board_state.board.shape
    from_index = action.from_square.index(shape.files)
    to_index = action.to_square.index(shape.files)
    if from_index == to_index:
        raise ValueError("cannot move to the same square")

    from_stack = _stack(state, from_index)
    if not from_stack or from_stack[-1].side is not turn.side:
        raise ValueError("cannot move from this square")

    moving = from_stack.pop()
    _sync_cell(state, from_index)

    opponent = _opponent_side(turn.side, state.extras.get("mode"))
    revealed_lines = _winning_lines(state, opponent)

    if not _can_land(moving, to_index, state):
        raise ValueError("cannot land on this square")

    _stack(state, to_index).append(moving)
    _sync_cell(state, to_index)
    return revealed_lines


def _hail_mary_blocks(
    action: MoveAction,
    lines: tuple[tuple[int, ...], ...],
    files: int,
) -> bool:
    from_index = action.from_square.index(files)
    to_index = action.to_square.index(files)
    for line in lines:
        if to_index in line and to_index != from_index:
            return True
    return False


def _hail_mary_destinations(
    from_index: int,
    piece: Piece,
    lines: tuple[tuple[int, ...], ...],
    state: GameState,
) -> set[int]:
    destinations: set[int] = set()
    for line in lines:
        for index in line:
            if index != from_index and _can_land(piece, index, state):
                destinations.add(index)
    return destinations


def _lift_probe(state: GameState, from_index: int) -> GameState:
    probe = state.clone(include_history=False)
    stack = _stack(probe, from_index)
    if stack:
        stack.pop()
    _sync_cell(probe, from_index)
    return probe


def _winning_lines(state: GameState, side: PieceSide) -> tuple[tuple[int, ...], ...]:
    winning: list[tuple[int, ...]] = []
    for line in LINES:
        if all(
            (piece := state.board_state.piece_at(index)) is not None
            and piece.side is side
            for index in line
        ):
            winning.append(line)
    return tuple(winning)


def _has_three_in_a_row(state: GameState, side: PieceSide) -> bool:
    return bool(_winning_lines(state, side))
