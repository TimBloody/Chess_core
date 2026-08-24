from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import HandsState
from chess_core.modes.chess import minichess
from chess_core.modes.shogi import dobutsu_shogi, shogi


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def test_minichess_has_gardner_array_and_legal_moves() -> None:
    mode = minichess()
    state = mode.initial_state()
    assert mode.board.shape.files == 5
    assert mode.board.shape.ranks == 5
    assert sum(piece is not None for piece in state.board_state.cells.values()) == 20
    assert state.board_state.piece_at(0).piece_type.name == "rook"
    assert state.board_state.piece_at(4).piece_type.name == "king"
    generator = MoveGenerator(mode)
    assert len(generator.generate_legal(state)) >= 5


def test_shogi_start_has_forty_pieces_and_nine_pawn_pushes() -> None:
    mode = shogi()
    state = mode.initial_state()
    assert mode.board.shape.cell_count == 81
    assert mode.drop_rule is not None
    assert mode.promotion_rule is not None
    assert sum(piece is not None for piece in state.board_state.cells.values()) == 40
    generator = MoveGenerator(mode)
    legal = generator.generate_legal(state)
    pawn_pushes = [
        action
        for action in legal
        if isinstance(action, MoveAction)
        and action.from_square.rank == 2
        and action.to_square.rank == 3
    ]
    assert len(pawn_pushes) == 9


def test_shogi_nifu_forbids_a_second_pawn_on_the_same_file() -> None:
    mode = shogi()
    state = mode.initial_state()
    state.hands = HandsState({PieceSide.WHITE: [_piece("pawn", PieceSide.WHITE)]})
    state.extras["mode"] = mode
    generator = MoveGenerator(mode)
    drops = [
        action
        for action in generator.generate_legal(state)
        if isinstance(action, DropAction) and action.piece_type.name == "pawn"
    ]
    occupied_files = {
        index % 9
        for index, piece in state.board_state.cells.items()
        if piece is not None
        and piece.side is PieceSide.WHITE
        and piece.piece_type.name == "pawn"
    }
    assert occupied_files == set(range(9))
    assert drops == []


def test_shogi_pawn_must_promote_on_the_last_rank() -> None:
    mode = shogi()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(81)}
    state.board_state.cells[4] = _piece("king", PieceSide.WHITE)
    state.board_state.cells[80] = _piece("king", PieceSide.BLACK)
    state.board_state.cells[67] = _piece("pawn", PieceSide.WHITE)
    state.extras["mode"] = mode
    generator = MoveGenerator(mode)
    legal = generator.generate_legal_for_square(state, 67)
    assert legal
    assert all(
        isinstance(action, MoveAction)
        and action.promotion_choice is not None
        and action.promotion_choice.name == "tokin"
        for action in legal
    )


def test_dobutsu_start_and_lion_try_wins() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    assert mode.board.shape.files == 3
    assert mode.board.shape.ranks == 4
    assert mode.royal_type == "lion"
    assert sum(piece is not None for piece in state.board_state.cells.values()) == 8
    generator = MoveGenerator(mode)
    assert generator.generate_legal(state)

    try_state = mode.initial_state()
    try_state.board_state.cells = {index: None for index in range(12)}
    try_state.board_state.cells[10] = _piece("lion", PieceSide.WHITE)
    try_state.board_state.cells[0] = _piece("lion", PieceSide.BLACK)
    try_state.side_to_move = PieceSide.BLACK
    try_state.extras["mode"] = mode
    game = LocalGameService(mode, try_state)
    assert game.status() is GameStatus.TRY_WIN


def test_dobutsu_capturing_the_lion_wins() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(12)}
    state.board_state.cells[1] = _piece("lion", PieceSide.WHITE)
    state.board_state.cells[4] = _piece("lion", PieceSide.BLACK)
    state.extras["mode"] = mode
    result = state.apply_turn(Turn(PieceSide.WHITE, [MoveAction(Square(1, 0), Square(1, 1))]))
    game = LocalGameService(mode, result)
    assert game.status() is GameStatus.KING_CAPTURE_WIN
