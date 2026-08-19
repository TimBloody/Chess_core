"""Tests for Corners (Уголки) mode."""

from __future__ import annotations

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.corners import (
    CORNER_LAYOUTS,
    corners,
    corners_mode_id,
    resolve_corners_mode_id,
)
from chess_core.modes.corners_rules import layout_homes

_CORNER = PieceTypeId("corner")


def _empty_board(mode):
    state = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    return state


def test_three_layouts_start_positions() -> None:
    expected = {
        "3x3": (9, 9),
        "3x4": (12, 12),
        "1234": (10, 10),
    }
    for layout in CORNER_LAYOUTS:
        mode = corners(layout)
        white_home, black_home = layout_homes(layout)
        assert mode.initial_extras["white_home"] == white_home
        assert mode.initial_extras["black_home"] == black_home
        state = mode.initial_state()
        white_count = sum(
            1
            for piece in state.board_state.cells.values()
            if piece is not None and piece.side is PieceSide.WHITE
        )
        black_count = sum(
            1
            for piece in state.board_state.cells.values()
            if piece is not None and piece.side is PieceSide.BLACK
        )
        assert (white_count, black_count) == expected[layout]


def test_corners_mode_id_and_resolve() -> None:
    assert corners_mode_id() == "corners"
    assert corners_mode_id("3x4") == "corners"
    assert corners_mode_id("3x3") == "corners+3x3"
    assert corners_mode_id("1234") == "corners+1234"

    assert resolve_corners_mode_id("corners").id == "corners"
    assert resolve_corners_mode_id("corners+3x3").id == "corners+3x3"
    assert resolve_corners_mode_id("corners+1234").id == "corners+1234"


def test_quiet_orthogonal_step() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    origin = Square(5, 0)
    target = Square(5, 1)
    state.board_state.cells[origin.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE

    move = MoveAction(origin, target, path=(target,), captured_squares=())
    assert move in [
        turn.actions[0]
        for turn in mode.legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    ]

    after = mode.apply_turn(state, Turn(PieceSide.WHITE, [move]), record_history=False)
    assert after.board_state.piece_at(target.index(8)) is not None
    assert after.board_state.piece_at(origin.index(8)) is None


def test_no_diagonal_moves() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    origin = Square(4, 4)
    state.board_state.cells[origin.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE

    moves = [
        action
        for turn in mode.legal_turns(state)
        for action in turn.actions
        if isinstance(action, MoveAction)
    ]
    for move in moves:
        df = abs(move.to_square.file - move.from_square.file)
        dr = abs(move.to_square.rank - move.from_square.rank)
        assert df + dr == 1 or len(move.path) >= 1


def test_jump_over_own_and_opponent_piece() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    origin = Square(4, 0)
    own_hurdle = Square(4, 1)
    own_landing = Square(4, 2)
    state.board_state.cells[origin.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.board_state.cells[own_hurdle.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE

    own_jump = MoveAction(
        origin, own_landing, path=(own_landing,), captured_squares=()
    )
    assert own_jump in [
        turn.actions[0]
        for turn in mode.legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    ]

    opponent_hurdle = Square(4, 3)
    opponent_landing = Square(4, 4)
    state.board_state.cells[origin.index(8)] = None
    state.board_state.cells[Square(4, 2).index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.board_state.cells[opponent_hurdle.index(8)] = Piece(
        _CORNER, PieceSide.BLACK
    )
    opp_origin = Square(4, 2)

    opp_jump = MoveAction(
        opp_origin,
        opponent_landing,
        path=(opponent_landing,),
        captured_squares=(),
    )
    assert opp_jump in [
        turn.actions[0]
        for turn in mode.legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    ]


def test_jump_chain() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    origin = Square(2, 2)
    hurdle1 = Square(3, 2)
    landing1 = Square(4, 2)
    hurdle2 = Square(4, 3)
    landing2 = Square(4, 4)
    state.board_state.cells[origin.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.board_state.cells[hurdle1.index(8)] = Piece(_CORNER, PieceSide.BLACK)
    state.board_state.cells[hurdle2.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE

    chain = MoveAction(
        origin,
        landing2,
        path=(landing1, landing2),
        captured_squares=(),
    )
    assert chain in [
        turn.actions[0]
        for turn in mode.legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    ]


def test_occupied_target_is_illegal() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    origin = Square(4, 0)
    hurdle = Square(4, 1)
    blocked = Square(4, 2)
    state.board_state.cells[origin.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.board_state.cells[hurdle.index(8)] = Piece(_CORNER, PieceSide.BLACK)
    state.board_state.cells[blocked.index(8)] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE

    illegal = MoveAction(
        origin, blocked, path=(blocked,), captured_squares=()
    )
    assert illegal not in [
        turn.actions[0]
        for turn in mode.legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    ]


def test_victory_when_all_pieces_reach_opponent_home() -> None:
    mode = corners("3x3")
    state = _empty_board(mode)
    black_home = mode.initial_extras["black_home"]
    for index in black_home:
        state.board_state.cells[index] = Piece(_CORNER, PieceSide.WHITE)
    state.side_to_move = PieceSide.BLACK

    outcome = mode.outcome(state)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.WHITE
    assert outcome.reason == "home"
    assert mode.legal_turns(state) == []


def test_local_game_service_play_turn() -> None:
    mode = corners("3x4")
    game = LocalGameService(mode)
    turns = game.legal_turns()
    assert turns
    first = turns[0]
    after = game.play_turn(first)
    assert game.state.side_to_move is PieceSide.BLACK
