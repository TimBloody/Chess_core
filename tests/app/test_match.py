"""Match-layer gift transfer and team result."""

from chess_core.app.match import MatchController, MatchPhase
from chess_core.app.seats import spec_by_id
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.bughouse import bughouse
from chess_core.modes.chess import classic_chess
from chess_core.tools.classical_demo import parse_move


class _Clock:
    def now_ms(self) -> int:
        return 0


def test_bughouse_capture_arrives_in_partner_hand() -> None:
    mode = bughouse()
    state = mode.initial_state()
    state.board_state.cells = {
        index: None for index in range(mode.board.shape.cell_count)
    }
    state.board_state.cells[4] = Piece(PieceTypeId("king"), PieceSide.WHITE)
    state.board_state.cells[60] = Piece(PieceTypeId("king"), PieceSide.BLACK)
    state.board_state.cells[3] = Piece(PieceTypeId("queen"), PieceSide.WHITE)  # d1
    state.board_state.cells[27] = Piece(PieceTypeId("pawn"), PieceSide.BLACK)  # d4
    match = MatchController(mode, state, clock=_Clock())
    match.start()
    white = spec_by_id("bughouse", "a_white")
    assert white is not None
    match.apply_turn(white, Turn(PieceSide.WHITE, [MoveAction(Square(3, 0), Square(3, 3))]))
    partner = match.board("B")
    assert partner.hands is not None
    assert partner.hands.count(PieceSide.BLACK, "pawn") == 1


def test_mate_on_one_board_ends_match() -> None:
    mode = bughouse()
    state = mode.initial_state()
    state.board_state.cells = {
        index: None for index in range(mode.board.shape.cell_count)
    }
    state.board_state.cells[41] = Piece(PieceTypeId("king"), PieceSide.WHITE)  # b6
    state.board_state.cells[58] = Piece(PieceTypeId("king"), PieceSide.BLACK)  # c8
    state.board_state.cells[10] = Piece(PieceTypeId("queen"), PieceSide.WHITE)  # c2
    match = MatchController(mode, state, clock=_Clock())
    match.start()
    white = spec_by_id("bughouse", "a_white")
    assert white is not None
    match.apply_turn(white, Turn(PieceSide.WHITE, [MoveAction(Square(2, 1), Square(2, 6))]))
    assert match.state.phase is MatchPhase.ENDED
    assert match.state.result is not None
    assert match.state.result.reason == "checkmate"


def test_threefold_ends_match_as_draw() -> None:
    mode = classic_chess()
    match = MatchController(mode, mode.initial_state(), clock=_Clock())
    match.start()
    white = spec_by_id("single", "white")
    black = spec_by_id("single", "black")
    assert white is not None and black is not None
    cycle = ("g1f3", "g8f6", "f3g1", "f6g8")
    for token in (*cycle, *cycle):
        mover = white if match.board("main").side_to_move is PieceSide.WHITE else black
        match.apply_turn(mover, Turn(mover.side, [parse_move(token)]))
    assert match.state.phase is MatchPhase.ENDED
    assert match.state.result is not None
    assert match.state.result.reason == "repetition"
    assert match.state.result.winner_team is None
