"""Contract tests for Gobblet Gobblers."""

from __future__ import annotations

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceAction, Turn
from chess_core.core.outcome import OutcomeStatus
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.state import GameState
from chess_core.modes.gobblet import gobblet
from chess_core.modes.gobblet_rules import (
    GOBBLET_LARGE,
    GOBBLET_MEDIUM,
    GOBBLET_SMALL,
    GobbletOptions,
    _stack,
    _sync_cell,
)


def _mode():
    return gobblet()


def _relocate_mode():
    return gobblet(GobbletOptions(allow_board_moves=True))


def _index(file: int, rank: int) -> int:
    return rank * 3 + file


def _place(
    state: GameState,
    side: PieceSide,
    piece_type,
    file: int,
    rank: int,
) -> None:
    index = _index(file, rank)
    _stack(state, index).append(Piece(piece_type, side))
    _sync_cell(state, index)


def _turn_place(side: PieceSide, piece_type, file: int, rank: int) -> Turn:
    return Turn(side, [PlaceAction(piece_type, Square(file, rank))])


def _turn_move(side: PieceSide, from_file: int, from_rank: int, to_file: int, to_rank: int) -> Turn:
    return Turn(
        side,
        [
            MoveAction(
                Square(from_file, from_rank),
                Square(to_file, to_rank),
            )
        ],
    )


def test_initial_reserve_is_two_each() -> None:
    mode = _mode()
    state = mode.initial_state()
    reserve = state.extras["reserve"]
    for side in (PieceSide.WHITE, PieceSide.BLACK):
        assert reserve[side][GOBBLET_SMALL] == 2
        assert reserve[side][GOBBLET_MEDIUM] == 2
        assert reserve[side][GOBBLET_LARGE] == 2


def test_place_from_reserve_on_empty_square() -> None:
    mode = _mode()
    state = mode.initial_state()
    turn = _turn_place(PieceSide.WHITE, GOBBLET_SMALL, 1, 1)
    after = mode.apply_turn(state, turn, record_history=False)
    assert after.board_state.piece_at(_index(1, 1)) is not None
    assert after.board_state.piece_at(_index(1, 1)).side is PieceSide.WHITE
    assert after.extras["reserve"][PieceSide.WHITE][GOBBLET_SMALL] == 1
    assert after.side_to_move is PieceSide.BLACK


def test_cannot_place_small_on_medium() -> None:
    mode = _mode()
    state = mode.initial_state()
    _place(state, PieceSide.BLACK, GOBBLET_MEDIUM, 0, 0)
    turn = _turn_place(PieceSide.WHITE, GOBBLET_SMALL, 0, 0)
    assert turn not in mode.legal_turns(state)


def test_large_covers_smaller_gobblet() -> None:
    mode = _mode()
    state = mode.initial_state()
    state = mode.apply_turn(
        state, _turn_place(PieceSide.WHITE, GOBBLET_MEDIUM, 1, 1), record_history=False
    )
    turn = _turn_place(PieceSide.BLACK, GOBBLET_LARGE, 1, 1)
    after = mode.apply_turn(state, turn, record_history=False)
    top = after.board_state.piece_at(_index(1, 1))
    assert top is not None
    assert top.piece_type == GOBBLET_LARGE
    assert len(_stack(after, _index(1, 1))) == 2


def test_default_gobblet_does_not_allow_board_moves() -> None:
    mode = _mode()
    state = mode.initial_state()
    state = mode.apply_turn(
        state, _turn_place(PieceSide.WHITE, GOBBLET_SMALL, 0, 0), record_history=False
    )
    assert state.side_to_move is PieceSide.BLACK
    state.side_to_move = PieceSide.WHITE
    turn = _turn_move(PieceSide.WHITE, 0, 0, 2, 2)
    assert turn not in mode.legal_turns(state)


def test_move_uncovers_hidden_piece() -> None:
    mode = _relocate_mode()
    state = mode.initial_state()
    index = _index(0, 0)
    _stack(state, index).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    _sync_cell(state, index)
    turn = _turn_move(PieceSide.WHITE, 0, 0, 2, 2)
    after = mode.apply_turn(state, turn, record_history=False)
    revealed = after.board_state.piece_at(index)
    assert revealed is not None
    assert revealed.side is PieceSide.BLACK
    assert revealed.piece_type == GOBBLET_SMALL


def test_three_in_a_row_wins() -> None:
    mode = _mode()
    state = mode.initial_state()
    _place(state, PieceSide.WHITE, GOBBLET_SMALL, 0, 0)
    _place(state, PieceSide.WHITE, GOBBLET_SMALL, 1, 0)
    turn = _turn_place(PieceSide.WHITE, GOBBLET_SMALL, 2, 0)
    after = mode.apply_turn(state, turn, record_history=False)
    outcome = mode.outcome(after)
    assert outcome.status is OutcomeStatus.WIN
    assert outcome.winner is PieceSide.WHITE
    assert outcome.reason == "three-in-a-row"


def test_reveal_without_hail_mary_omits_source() -> None:
    mode = _relocate_mode()
    state = mode.initial_state()
    # Lifting white large from (1,0) reveals a black row; (0,0) and (2,0) tops
    # are black larges that cannot be gobbled by the moving white large.
    _stack(state, _index(0, 0)).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.BLACK),
        ]
    )
    _sync_cell(state, _index(0, 0))
    _stack(state, _index(1, 0)).extend(
        [
            Piece(GOBBLET_MEDIUM, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    _sync_cell(state, _index(1, 0))
    _stack(state, _index(2, 0)).extend(
        [
            Piece(GOBBLET_SMALL, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.BLACK),
        ]
    )
    _sync_cell(state, _index(2, 0))
    state.side_to_move = PieceSide.WHITE

    legal = mode.legal_turns(state)
    sources = {
        turn.actions[0].from_square
        for turn in legal
        if isinstance(turn.actions[0], MoveAction)
    }
    assert Square(1, 0) not in sources


def test_hail_mary_blocks_revealed_line() -> None:
    mode = _relocate_mode()
    state = mode.initial_state()
    _stack(state, _index(0, 0)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    _sync_cell(state, _index(0, 0))
    _stack(state, _index(1, 0)).extend(
        [
            Piece(GOBBLET_MEDIUM, PieceSide.BLACK),
            Piece(GOBBLET_LARGE, PieceSide.WHITE),
        ]
    )
    _sync_cell(state, _index(1, 0))
    _stack(state, _index(2, 0)).append(Piece(GOBBLET_SMALL, PieceSide.BLACK))
    _sync_cell(state, _index(2, 0))
    state.side_to_move = PieceSide.WHITE

    turn = _turn_move(PieceSide.WHITE, 1, 0, 0, 0)
    assert turn in mode.legal_turns(state)
    after = mode.apply_turn(state, turn, record_history=False)
    outcome = mode.outcome(after)
    assert outcome.status is OutcomeStatus.ACTIVE
    assert not _has_visible_line(after, PieceSide.BLACK)


def test_cannot_move_to_same_square() -> None:
    mode = _relocate_mode()
    state = mode.initial_state()
    state = mode.apply_turn(
        state, _turn_place(PieceSide.WHITE, GOBBLET_SMALL, 1, 1), record_history=False
    )
    turn = _turn_move(PieceSide.WHITE, 1, 1, 1, 1)
    assert turn not in mode.legal_turns(state)


def test_local_game_service_play_turn_place() -> None:
    mode = _mode()
    game = LocalGameService(mode)
    game.play_turn(_turn_place(PieceSide.WHITE, GOBBLET_MEDIUM, 0, 0))
    assert game.state.board_state.piece_at(_index(0, 0)) is not None
    assert game.state.side_to_move is PieceSide.BLACK
    assert len(game.move_log) == 1


def _has_visible_line(state: GameState, side: PieceSide) -> bool:
    lines = (
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    )
    for line in lines:
        if all(
            (piece := state.board_state.piece_at(index)) is not None
            and piece.side is side
            for index in line
        ):
            return True
    return False
