"""Contract tests for Gobblet Gobblers."""

from __future__ import annotations

from chess_core.app.game import GameStatus, LocalGameService, evaluate_status, line_winner
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.modes.gobblet import gobblet
from chess_core.modes.gobblet_rules import (
    GOBBLET_LARGE,
    GOBBLET_MEDIUM,
    GOBBLET_SMALL,
    stack_at,
    sync_cell,
)


def _index(file: int, rank: int) -> int:
    return rank * 3 + file


def _legal_turns(state: GameState) -> list[Turn]:
    mode = state.extras["mode"]
    return [Turn(state.side_to_move, [action]) for action in MoveGenerator(mode).generate_legal(state)]


def _place(state: GameState, side: PieceSide, piece_type, file: int, rank: int) -> None:
    index = _index(file, rank)
    stack_at(state, index).append(Piece(piece_type, side))
    sync_cell(state, index)


def _turn_drop(side: PieceSide, piece_type, file: int, rank: int) -> Turn:
    return Turn(side, [DropAction(piece_type, Square(file, rank))])


def _turn_move(side: PieceSide, from_file: int, from_rank: int, to_file: int, to_rank: int) -> Turn:
    return Turn(side, [MoveAction(Square(from_file, from_rank), Square(to_file, to_rank))])


def test_initial_reserve_is_two_each() -> None:
    state = gobblet().initial_state()
    assert state.hands is not None
    for side in (PieceSide.WHITE, PieceSide.BLACK):
        assert state.hands.count(side, "gobblet_small") == 2
        assert state.hands.count(side, "gobblet_medium") == 2
        assert state.hands.count(side, "gobblet_large") == 2


def test_place_from_reserve_on_empty_square() -> None:
    mode = gobblet()
    state = mode.initial_state()
    after = state.apply_turn(_turn_drop(PieceSide.WHITE, GOBBLET_SMALL, 1, 1), record_history=False)
    top = after.board_state.piece_at(_index(1, 1))
    assert top is not None
    assert top.side is PieceSide.WHITE
    assert after.hands is not None
    assert after.hands.count(PieceSide.WHITE, "gobblet_small") == 1
    assert after.side_to_move is PieceSide.BLACK


def test_cannot_place_small_on_medium() -> None:
    state = gobblet().initial_state()
    _place(state, PieceSide.BLACK, GOBBLET_MEDIUM, 0, 0)
    turn = _turn_drop(PieceSide.WHITE, GOBBLET_SMALL, 0, 0)
    assert turn not in _legal_turns(state)


def test_large_covers_smaller_gobblet() -> None:
    mode = gobblet()
    state = mode.initial_state()
    state = state.apply_turn(
        _turn_drop(PieceSide.WHITE, GOBBLET_MEDIUM, 1, 1), record_history=False
    )
    after = state.apply_turn(
        _turn_drop(PieceSide.BLACK, GOBBLET_LARGE, 1, 1), record_history=False
    )
    top = after.board_state.piece_at(_index(1, 1))
    assert top is not None
    assert top.piece_type == GOBBLET_LARGE
    assert len(stack_at(after, _index(1, 1))) == 2


def test_board_move_is_legal() -> None:
    mode = gobblet()
    state = mode.initial_state()
    state = state.apply_turn(
        _turn_drop(PieceSide.WHITE, GOBBLET_SMALL, 0, 0), record_history=False
    )
    state.side_to_move = PieceSide.WHITE
    turn = _turn_move(PieceSide.WHITE, 0, 0, 2, 2)
    assert turn in _legal_turns(state)


def test_move_uncovers_hidden_piece() -> None:
    mode = gobblet()
    state = mode.initial_state()
    index = _index(0, 0)
    stack_at(state, index).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    sync_cell(state, index)
    after = state.apply_turn(_turn_move(PieceSide.WHITE, 0, 0, 2, 2), record_history=False)
    revealed = after.board_state.piece_at(index)
    assert revealed is not None
    assert revealed.side is PieceSide.BLACK
    assert revealed.piece_type == GOBBLET_SMALL


def test_three_in_a_row_wins() -> None:
    mode = gobblet()
    state = mode.initial_state()
    _place(state, PieceSide.WHITE, GOBBLET_SMALL, 0, 0)
    _place(state, PieceSide.WHITE, GOBBLET_SMALL, 1, 0)
    after = state.apply_turn(
        _turn_drop(PieceSide.WHITE, GOBBLET_SMALL, 2, 0), record_history=False
    )
    status = evaluate_status(mode, MoveGenerator(mode), after, is_live=True)
    assert status is GameStatus.TRY_WIN
    assert line_winner(mode, after) is PieceSide.WHITE


def test_reveal_without_hail_mary_omits_source() -> None:
    state = gobblet().initial_state()
    stack_at(state, _index(0, 0)).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.BLACK),
        ]
    )
    sync_cell(state, _index(0, 0))
    stack_at(state, _index(1, 0)).extend(
        [
            Piece(GOBBLET_MEDIUM, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    sync_cell(state, _index(1, 0))
    stack_at(state, _index(2, 0)).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.BLACK),
        ]
    )
    sync_cell(state, _index(2, 0))
    sources = {
        turn.actions[0].from_square
        for turn in _legal_turns(state)
        if isinstance(turn.actions[0], MoveAction)
    }
    assert Square(1, 0) not in sources


def test_hail_mary_blocks_revealed_line() -> None:
    mode = gobblet()
    state = mode.initial_state()
    stack_at(state, _index(0, 0)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    sync_cell(state, _index(0, 0))
    stack_at(state, _index(1, 0)).extend(
        [
            Piece(GOBBLET_MEDIUM, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    sync_cell(state, _index(1, 0))
    stack_at(state, _index(2, 0)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    sync_cell(state, _index(2, 0))

    turn = _turn_move(PieceSide.WHITE, 1, 0, 0, 0)
    assert turn in _legal_turns(state)
    after = state.apply_turn(turn, record_history=False)
    status = evaluate_status(mode, MoveGenerator(mode), after, is_live=True)
    assert status is GameStatus.ACTIVE
    assert line_winner(mode, after) is None


def test_cannot_move_to_same_square() -> None:
    state = gobblet().initial_state()
    state = state.apply_turn(
        _turn_drop(PieceSide.WHITE, GOBBLET_SMALL, 1, 1), record_history=False
    )
    state.side_to_move = PieceSide.WHITE
    turn = _turn_move(PieceSide.WHITE, 1, 1, 1, 1)
    assert turn not in _legal_turns(state)


def test_local_game_service_play_turn_place() -> None:
    game = LocalGameService(gobblet())
    game.play_turn(_turn_drop(PieceSide.WHITE, GOBBLET_MEDIUM, 0, 0))
    assert game.state.board_state.piece_at(_index(0, 0)) is not None
    assert game.state.side_to_move is PieceSide.BLACK
    assert len(game.move_log) == 1


def test_gobblet_export_transcript_uses_shared_journal() -> None:
    from datetime import datetime

    game = LocalGameService(gobblet())
    game.play_turn(_turn_drop(PieceSide.WHITE, GOBBLET_MEDIUM, 0, 0))
    text = game.export_transcript(exported_at=datetime(2026, 8, 31, 16, 40))
    assert '[Mode "gobblet"]' in text
    assert game.move_log[0] in text
    assert '[Result "*"]' in text
    assert "партия не окончена" in text
