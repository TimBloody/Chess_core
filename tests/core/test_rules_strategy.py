"""Tests for GameOutcome and default rules strategy outcome mapping."""

from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules_strategy import DefaultRulesStrategy
from chess_core.modes.chess import classic_chess


def test_default_outcome_active_at_start() -> None:
    mode = classic_chess()
    strategy = DefaultRulesStrategy(mode)
    outcome = strategy.outcome(mode.initial_state())
    assert outcome.status is OutcomeStatus.ACTIVE
    assert outcome.winner is None


def test_default_outcome_checkmate() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    state.board_state.cells[4] = Piece(PieceTypeId("king"), PieceSide.WHITE)
    state.board_state.cells[12] = Piece(PieceTypeId("queen"), PieceSide.BLACK)
    state.board_state.cells[20] = Piece(PieceTypeId("king"), PieceSide.BLACK)
    state.side_to_move = PieceSide.WHITE

    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.BLACK
    assert outcome.reason == "checkmate"


def test_mode_legal_turns_wrap_single_moves() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turns = mode.legal_turns(state)
    assert turns
    assert all(len(turn.actions) == 1 for turn in turns)
    assert all(isinstance(turn.actions[0], MoveAction) for turn in turns)
