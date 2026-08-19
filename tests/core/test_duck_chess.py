import pytest

from chess_core.core.blockers import (
    BLOCKER_TYPE_NAME,
    blocker_index,
    blocker_square,
    legal_blocker_actions,
    legal_blocker_squares,
)
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceBlockerAction, Turn
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import duck_chess


def _sq(name: str) -> Square:
    return Square(file=ord(name[0]) - ord("a"), rank=int(name[1]) - 1)


def _empty_squares(state) -> list[Square]:
    shape = state.board_state.board.shape
    return [
        Square.from_index(index, shape.files, shape.ranks)
        for index in range(shape.cell_count)
        if state.board_state.piece_at(index) is None
    ]


def _e2e4_duck_on_e5():
    return duck_chess().initial_state().apply_turn(
        Turn(
            PieceSide.WHITE,
            [
                MoveAction(_sq("e2"), _sq("e4")),
                PlaceBlockerAction(_sq("e5")),
            ],
        )
    )


def test_initial_duck_is_off_board_with_thirty_two_legal_squares() -> None:
    state = duck_chess().initial_state()
    empties = _empty_squares(state)

    assert blocker_index(state) is None
    assert blocker_square(state) is None
    assert len(empties) == 32
    assert legal_blocker_squares(state) == empties


def test_after_e2e4_and_duck_on_e5_queries_and_legal_squares() -> None:
    state = _e2e4_duck_on_e5()
    files = state.board_state.board.shape.files
    legal = legal_blocker_squares(state)

    assert blocker_square(state) == _sq("e5")
    assert blocker_index(state) == _sq("e5").index(files)
    assert _sq("e5") not in legal
    assert _sq("e2") in legal
    assert _sq("e4") not in legal
    assert _sq("a1") not in legal
    assert all(state.board_state.piece_at(square.index(files)) is None for square in legal)
    assert len(legal) == 31


def test_duck_cannot_stay_on_e5() -> None:
    state = _e2e4_duck_on_e5()
    assert _sq("e5") not in legal_blocker_squares(state)


def test_place_blocker_on_occupied_square_raises() -> None:
    with pytest.raises(ValueError, match="occupied"):
        duck_chess().initial_state().apply_turn(
            Turn(
                PieceSide.WHITE,
                [
                    MoveAction(_sq("e2"), _sq("e4")),
                    PlaceBlockerAction(_sq("e4")),
                ],
            )
        )


def test_blocker_index_raises_when_two_ducks_present() -> None:
    state = duck_chess().initial_state().clone()
    files = state.board_state.board.shape.files
    state.board_state.cells[_sq("a3").index(files)] = Piece(
        PieceTypeId(BLOCKER_TYPE_NAME), PieceSide.NEUTRAL
    )
    state.board_state.cells[_sq("b3").index(files)] = Piece(
        PieceTypeId(BLOCKER_TYPE_NAME), PieceSide.NEUTRAL
    )

    with pytest.raises(ValueError):
        blocker_index(state)


def test_legal_blocker_actions_match_squares() -> None:
    start = duck_chess().initial_state()
    after = _e2e4_duck_on_e5()

    for state in (start, after):
        squares = legal_blocker_squares(state)
        actions = legal_blocker_actions(state)
        assert [action.square for action in actions] == squares
        assert all(isinstance(action, PlaceBlockerAction) for action in actions)


def test_cloned_state_can_place_and_query_blocker() -> None:
    state = duck_chess().initial_state().clone()
    files = state.board_state.board.shape.files
    duck_square = _sq("c6")
    state.board_state.cells[duck_square.index(files)] = Piece(
        PieceTypeId(BLOCKER_TYPE_NAME), PieceSide.NEUTRAL
    )

    assert blocker_index(state) == duck_square.index(files)
    assert blocker_square(state) == duck_square
    legal = legal_blocker_squares(state)
    assert duck_square not in legal
    assert _sq("e4") in legal
    assert _sq("a1") not in legal


def test_incomplete_turn_without_blocker_still_raises() -> None:
    duck = duck_chess()
    incomplete = Turn(
        PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 2))]
    )
    with pytest.raises(ValueError, match="scenario"):
        duck.initial_state().apply_turn(incomplete)
