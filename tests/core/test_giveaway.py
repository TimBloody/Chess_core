from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import giveaway


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def test_giveaway_must_capture_when_a_capture_exists() -> None:
    mode = giveaway()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(64)}
    state.board_state.cells[12] = _piece("rook", PieceSide.WHITE)
    state.board_state.cells[20] = _piece("pawn", PieceSide.BLACK)
    state.board_state.cells[4] = _piece("king", PieceSide.WHITE)
    state.board_state.cells[60] = _piece("king", PieceSide.BLACK)
    state.extras["mode"] = mode
    generator = MoveGenerator(mode)
    legal = generator.generate_legal(state)
    assert MoveAction(Square(4, 1), Square(4, 2)) in legal
    assert all(action.to_square == Square(4, 2) for action in legal)
    king_moves = generator.generate_legal_for_square(state, Square(4, 0))
    assert king_moves == []
    rook_moves = generator.generate_legal_for_square(state, Square(4, 1))
    assert rook_moves == [MoveAction(Square(4, 1), Square(4, 2))]


def test_giveaway_losing_the_last_piece_wins() -> None:
    mode = giveaway()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(64)}
    state.board_state.cells[8] = _piece("pawn", PieceSide.WHITE)
    state.board_state.cells[17] = _piece("pawn", PieceSide.BLACK)
    state.board_state.cells[60] = _piece("king", PieceSide.BLACK)
    state.side_to_move = PieceSide.BLACK
    state.extras["mode"] = mode
    result = state.apply_turn(Turn(PieceSide.BLACK, [MoveAction(Square(1, 2), Square(0, 1))]))
    game = LocalGameService(mode, result)
    assert game.status() is GameStatus.MATERIAL_WIN


def test_giveaway_stalemate_is_a_win_for_the_side_to_move() -> None:
    mode = giveaway()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(64)}
    state.board_state.cells[0] = _piece("pawn", PieceSide.WHITE)
    state.board_state.cells[8] = _piece("pawn", PieceSide.BLACK)
    state.board_state.cells[16] = _piece("king", PieceSide.BLACK)
    state.extras["mode"] = mode
    game = LocalGameService(mode, state)
    assert not MoveGenerator(mode).has_any_legal(state)
    assert game.status() is GameStatus.MATERIAL_WIN


def test_giveaway_pawn_may_promote_to_king() -> None:
    from chess_core.core.notation import parse_fen

    mode = giveaway()
    state = parse_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", mode)
    legal = MoveGenerator(mode).generate_legal_for_square(state, Square(0, 6))
    assert {action.promotion_choice.name for action in legal} == {
        "queen",
        "rook",
        "bishop",
        "knight",
        "king",
    }
