"""Hand & Brain piece-type filter."""

from chess_core.app.match import MatchController
from chess_core.app.seats import spec_by_id
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.hand_and_brain import hand_and_brain


class _Clock:
    def now_ms(self) -> int:
        return 0


def test_two_knights_selecting_one_allows_either() -> None:
    mode = hand_and_brain()
    state = mode.initial_state()
    state.board_state.cells = {
        index: None for index in range(mode.board.shape.cell_count)
    }
    state.board_state.cells[4] = Piece(PieceTypeId("king"), PieceSide.WHITE)
    state.board_state.cells[60] = Piece(PieceTypeId("king"), PieceSide.BLACK)
    state.board_state.cells[6] = Piece(PieceTypeId("knight"), PieceSide.WHITE)  # g1
    state.board_state.cells[1] = Piece(PieceTypeId("knight"), PieceSide.WHITE)  # b1
    match = MatchController(mode, state, clock=_Clock())
    match.start()
    brain = spec_by_id("hand_and_brain", "white_brain")
    hand = spec_by_id("hand_and_brain", "white_hand")
    assert brain is not None and hand is not None
    match.brain_select(brain, "knight")
    legal = match.legal_actions("main", chosen_type="knight")
    origins = {action.from_square.index(8) for action in legal if hasattr(action, "from_square")}
    assert 6 in origins
    assert 1 in origins
    match.apply_turn(hand, Turn(PieceSide.WHITE, [MoveAction(Square(1, 0), Square(2, 2))]))
    assert match.board("main").board_state.piece_at(18) is not None


def test_hand_cannot_move_before_brain_select() -> None:
    mode = hand_and_brain()
    match = MatchController(mode, mode.initial_state(), clock=_Clock())
    match.start()
    hand = spec_by_id("hand_and_brain", "white_hand")
    assert hand is not None
    try:
        match.apply_turn(
            hand,
            Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        )
    except PermissionError:
        return
    raise AssertionError("expected PermissionError")
