"""Gobblet Gobblers: cover-larger drops/moves and hail-mary relocation."""

from __future__ import annotations

from chess_core.core.move import MoveAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState, _cell_stack, _sync_stack_cell

GOBBLET_SMALL = PieceTypeId("gobblet_small")
GOBBLET_MEDIUM = PieceTypeId("gobblet_medium")
GOBBLET_LARGE = PieceTypeId("gobblet_large")

GOBBLET_TYPES = (GOBBLET_SMALL, GOBBLET_MEDIUM, GOBBLET_LARGE)
GOBBLET_SIZES = {
    "gobblet_small": 1,
    "gobblet_medium": 2,
    "gobblet_large": 3,
}

ALIGN_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


class GobbletDropRule:
    def can_drop(self, piece_type: PieceTypeId, square_index: int, state: object) -> bool:
        if not isinstance(state, GameState):
            return False
        top = state.board_state.piece_at(square_index)
        if top is None:
            return True
        return GOBBLET_SIZES.get(piece_type.name, 0) > GOBBLET_SIZES.get(top.piece_type.name, 0)

    def allowed_faces(self, piece_type: PieceTypeId) -> tuple[str, ...] | None:
        del piece_type
        return None

    def captured_as(self, piece: Piece) -> Piece:
        return piece


class GobbletHailMary:
    """A lift that reveals the opponent's line may only land on that line."""

    def filter_legal(self, pseudo_moves: list, state: object) -> list:
        if not isinstance(state, GameState):
            return pseudo_moves
        opponent = state.side_to_move.opponent()
        legal = []
        for action in pseudo_moves:
            if not isinstance(action, MoveAction):
                legal.append(action)
                continue
            files = state.board_state.board.shape.files
            from_index = action.from_square.index(files)
            probe = _lift_probe(state, from_index)
            lines = _winning_lines(probe, opponent)
            if not lines:
                legal.append(action)
                continue
            to_index = action.to_square.index(files)
            if any(to_index in line for line in lines):
                legal.append(action)
        return legal


def stack_at(state: GameState, index: int) -> list[Piece]:
    return _cell_stack(state, index)


def sync_cell(state: GameState, index: int) -> None:
    _sync_stack_cell(state, index)


def _lift_probe(state: GameState, from_index: int) -> GameState:
    probe = state.clone(include_history=False)
    stack = _cell_stack(probe, from_index)
    if stack:
        stack.pop()
    _sync_stack_cell(probe, from_index)
    return probe


def _winning_lines(state: GameState, side: PieceSide) -> tuple[tuple[int, ...], ...]:
    winning: list[tuple[int, ...]] = []
    for line in ALIGN_LINES:
        if all(
            (piece := state.board_state.piece_at(index)) is not None and piece.side is side
            for index in line
        ):
            winning.append(line)
    return tuple(winning)
