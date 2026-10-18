from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction, PassAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.board_games import corners, draughts, reversi


def test_board_games_are_registered_for_the_mode_menu() -> None:
    register_builtin_modes()
    modes = default_registry.list_modes()
    assert {"reversi", "corners", "draughts", "gobblet", "nanai_checkers", "hasami_shogi"} <= set(modes)
    assert "othello" not in modes


def test_reversi_opening_has_four_flipping_drops() -> None:
    mode = reversi()
    state = mode.initial_state()
    generator = MoveGenerator(mode)
    drops = [action for action in generator.generate_legal(state) if isinstance(action, DropAction)]
    squares = {(action.to_square.file, action.to_square.rank) for action in drops}
    assert squares == {(2, 3), (3, 2), (4, 5), (5, 4)}
    after = state.apply_turn(Turn(PieceSide.WHITE, [DropAction(PieceTypeId("disc"), Square(2, 3))]))
    assert after.board_state.piece_at(26).side is PieceSide.WHITE
    assert after.board_state.piece_at(27).side is PieceSide.WHITE


def test_reversi_pass_when_only_the_opponent_can_drop() -> None:
    mode = reversi()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(64)}
    disc = PieceTypeId("disc")
    state.board_state.cells[0] = Piece(disc, PieceSide.BLACK)
    state.board_state.cells[8] = Piece(disc, PieceSide.WHITE)
    state.side_to_move = PieceSide.WHITE
    state.extras["mode"] = mode
    legal = MoveGenerator(mode).generate_legal(state)
    assert legal == [PassAction()]


def test_corners_start_has_nine_men_and_a_step() -> None:
    mode = corners()
    state = mode.initial_state()
    white = sum(
        1
        for piece in state.board_state.cells.values()
        if piece is not None and piece.side is PieceSide.WHITE
    )
    assert white == 9
    steps = MoveGenerator(mode).generate_legal_for_square(state, Square(2, 2))
    assert MoveAction(Square(2, 2), Square(3, 2)) in steps
    assert MoveAction(Square(2, 2), Square(2, 3)) in steps


def test_corners_occupying_the_opposite_corner_wins() -> None:
    mode = corners()
    state = mode.initial_state()
    state.board_state.cells = {index: None for index in range(64)}
    man = PieceTypeId("man")
    for rank in range(5, 8):
        for file in range(5, 8):
            if (file, rank) == (5, 5):
                continue
            state.board_state.cells[rank * 8 + file] = Piece(man, PieceSide.WHITE)
    state.board_state.cells[4 * 8 + 5] = Piece(man, PieceSide.WHITE)
    state.board_state.cells[0] = Piece(man, PieceSide.BLACK)
    state.extras["mode"] = mode
    result = state.apply_turn(Turn(PieceSide.WHITE, [MoveAction(Square(5, 4), Square(5, 5))]))
    assert LocalGameService(mode, result).status() is GameStatus.TRY_WIN


def test_draughts_start_has_twelve_men_and_must_jump() -> None:
    mode = draughts()
    state = mode.initial_state()
    white = [
        index
        for index, piece in state.board_state.cells.items()
        if piece is not None and piece.side is PieceSide.WHITE
    ]
    assert len(white) == 12
    assert MoveGenerator(mode).generate_legal(state)

    state.board_state.cells = {index: None for index in range(64)}
    state.board_state.cells[18] = Piece(PieceTypeId("man"), PieceSide.WHITE)
    state.board_state.cells[27] = Piece(PieceTypeId("man"), PieceSide.BLACK)
    state.extras["mode"] = mode
    legal = MoveGenerator(mode).generate_legal(state)
    assert len(legal) == 1
    move = legal[0]
    assert isinstance(move, MoveAction)
    assert move.to_square == Square(4, 4)
    assert move.jumped == (Square(3, 3),)
