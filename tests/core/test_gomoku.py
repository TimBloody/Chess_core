"""Contract tests for freestyle Gomoku."""

from __future__ import annotations

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import PlaceAction, Turn
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.modes.gomoku import gomoku
from chess_core.modes.gomoku_rules import STONE


def _mode():
    return gomoku()


def _index(file: int, rank: int) -> int:
    return rank * 15 + file


def _place(state: GameState, side: PieceSide, file: int, rank: int) -> None:
    state.board_state.cells[_index(file, rank)] = Piece(STONE, side)


def _turn(side: PieceSide, file: int, rank: int) -> Turn:
    return Turn(side, [PlaceAction(STONE, Square(file, rank))])


def test_initial_state_is_15x15_black_to_move() -> None:
    mode = _mode()
    state = mode.initial_state()
    assert mode.board.shape.files == 15
    assert mode.board.shape.ranks == 15
    assert mode.board.shape.cell_count == 225
    assert state.side_to_move is PieceSide.BLACK
    assert all(piece is None for piece in state.board_state.cells.values())


def test_place_stone_on_empty_square() -> None:
    mode = _mode()
    state = mode.initial_state()
    turn = _turn(PieceSide.BLACK, 7, 7)
    after = mode.apply_turn(state, turn, record_history=False)
    assert after.board_state.piece_at(_index(7, 7)) is not None
    assert after.board_state.piece_at(_index(7, 7)).side is PieceSide.BLACK
    assert after.side_to_move is PieceSide.WHITE


def test_occupied_square_is_not_legal() -> None:
    mode = _mode()
    state = mode.initial_state()
    state = mode.apply_turn(state, _turn(PieceSide.BLACK, 3, 3), record_history=False)
    assert _turn(PieceSide.WHITE, 3, 3) not in mode.legal_turns(state)


def test_five_in_a_row_wins_horizontal_vertical_diagonal() -> None:
    mode = _mode()
    cases = [
        [(file, 5) for file in range(5)],
        [(4, rank) for rank in range(5)],
        [(rank, rank) for rank in range(5)],
        [(rank, 4 - rank) for rank in range(5)],
    ]
    for coords in cases:
        state = mode.initial_state()
        for file, rank in coords:
            _place(state, PieceSide.BLACK, file, rank)
        outcome = mode.outcome(state)
        assert outcome.status is OutcomeStatus.WIN
        assert outcome.winner is PieceSide.BLACK
        assert outcome.reason == "five-in-a-row"


def test_overline_six_or_more_wins() -> None:
    mode = _mode()
    state = mode.initial_state()
    for file in range(6):
        _place(state, PieceSide.WHITE, file, 0)
    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.WHITE
    assert outcome.reason == "five-in-a-row"


def test_four_in_a_row_is_not_a_win() -> None:
    mode = _mode()
    state = mode.initial_state()
    for file in range(4):
        _place(state, PieceSide.BLACK, file, 2)
    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.ACTIVE
    assert outcome.winner is None


def test_full_board_without_line_is_draw() -> None:
    mode = _mode()
    state = mode.initial_state()
    for rank in range(15):
        for file in range(15):
            side = (
                PieceSide.BLACK
                if ((file + rank * 4) % 8) < 4
                else PieceSide.WHITE
            )
            _place(state, side, file, rank)
    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.DRAW
    assert outcome.reason == "board-full"


def test_legal_turns_empty_after_win() -> None:
    mode = _mode()
    state = mode.initial_state()
    for file in range(5):
        _place(state, PieceSide.BLACK, file, 8)
    assert mode.outcome(state).status is OutcomeStatus.WIN
    assert mode.legal_turns(state) == []


def test_local_game_service_play_turn() -> None:
    mode = _mode()
    game = LocalGameService(mode)
    assert game.state.side_to_move is PieceSide.BLACK
    game.play_turn(_turn(PieceSide.BLACK, 7, 7))
    assert game.state.board_state.piece_at(_index(7, 7)) is not None
    assert game.state.side_to_move is PieceSide.WHITE
    assert len(game.move_log) == 1
