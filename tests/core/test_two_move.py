from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import two_move_chess


def _sq(name: str) -> Square:
    return Square(file=ord(name[0]) - ord("a"), rank=int(name[1]) - 1)


def test_start_has_twenty_legal_moves() -> None:
    mode = two_move_chess()
    state = mode.initial_state()
    assert len(MoveGenerator(mode).generate_legal(state)) == 20


def test_white_first_move_commits_immediately() -> None:
    game = LocalGameService(two_move_chess())
    game.play(MoveAction(_sq("e2"), _sq("e4")))
    assert game.state.side_to_move is PieceSide.BLACK
    assert not game.pending_actions


def test_black_needs_two_moves_before_side_switches() -> None:
    game = LocalGameService(two_move_chess())
    game.play(MoveAction(_sq("e2"), _sq("e4")))
    game.play(MoveAction(_sq("e7"), _sq("e5")))
    assert game.state.side_to_move is PieceSide.BLACK
    assert len(game.pending_actions) == 1
    game.play(MoveAction(_sq("d7"), _sq("d5")))
    assert game.state.side_to_move is PieceSide.WHITE
    assert not game.pending_actions


def test_same_piece_can_move_twice_in_one_turn() -> None:
    game = LocalGameService(two_move_chess())
    game.play(MoveAction(_sq("e2"), _sq("e4")))
    game.play(MoveAction(_sq("b8"), _sq("c6")))
    assert len(game.pending_actions) == 1
    visible = game.visible_state()
    files = game.mode.board.shape.files
    assert visible.board_state.piece_at(_sq("c6").index(files)) is not None
    assert visible.board_state.piece_at(_sq("b8").index(files)) is None
    game.play(MoveAction(_sq("c6"), _sq("a5")))
    assert game.state.side_to_move is PieceSide.WHITE
    assert not game.pending_actions
    knight = game.state.board_state.piece_at(_sq("a5").index(files))
    assert knight is not None
    assert knight.piece_type.name == "knight"


def test_check_on_first_of_two_ends_turn() -> None:
    mode = two_move_chess()
    state = mode.initial_state()
    files = mode.board.shape.files
    state.board_state.cells[_sq("e2").index(files)] = None
    state.board_state.cells[_sq("e4").index(files)] = Piece(
        PieceTypeId("pawn"), PieceSide.WHITE
    )
    state.board_state.cells[_sq("e7").index(files)] = None
    state.board_state.cells[_sq("f2").index(files)] = None
    state.side_to_move = PieceSide.BLACK
    state.extras["committed_turns"] = 1
    game = LocalGameService(mode, initial_state=state)
    game.play(MoveAction(_sq("d8"), _sq("h4")))
    assert game.state.side_to_move is PieceSide.WHITE
    assert not game.pending_actions


def test_started_in_check_allows_only_one_move() -> None:
    mode = two_move_chess()
    state = mode.initial_state()
    files = mode.board.shape.files
    for index in range(64):
        state.board_state.cells[index] = None
    state.board_state.cells[_sq("e1").index(files)] = Piece(
        PieceTypeId("king"), PieceSide.WHITE
    )
    state.board_state.cells[_sq("e8").index(files)] = Piece(
        PieceTypeId("king"), PieceSide.BLACK
    )
    state.board_state.cells[_sq("e3").index(files)] = Piece(
        PieceTypeId("queen"), PieceSide.BLACK
    )
    game = LocalGameService(mode, initial_state=state)
    game.play(MoveAction(_sq("e1"), _sq("d1")))
    assert game.state.side_to_move is PieceSide.BLACK
    assert not game.pending_actions
