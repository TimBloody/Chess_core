"""Three-check chess mode contracts."""

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryKind
from chess_core.modes.chess import three_check_chess


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def _clear(state, cells: dict[int, Piece], side: PieceSide) -> None:
    state.board_state.cells = {
        index: cells.get(index) for index in range(state.board_state.board.shape.cell_count)
    }
    state.side_to_move = side


def test_three_check_start_has_twenty_legal_moves() -> None:
    mode = three_check_chess()
    state = mode.initial_state()
    assert not mode.is_dummy
    assert mode.modifier_ids == ("three_check",)
    assert VictoryKind.THREE_CHECK in mode.victory_kinds()
    assert state.extras["checks_given"] == {"white": 0, "black": 0}
    assert len(MoveGenerator(mode).generate_legal(state)) == 20


def test_three_check_wins_on_third_check() -> None:
    mode = three_check_chess()
    state = mode.initial_state()
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            3: _piece("queen", PieceSide.WHITE),
            60: _piece("king", PieceSide.BLACK),
        },
        PieceSide.WHITE,
    )
    state.extras["checks_given"] = {"white": 2, "black": 0}
    state.extras["castling_rights"] = set()
    game = LocalGameService(mode, initial_state=state)
    game.play(MoveAction(Square(3, 0), Square(3, 7)))
    assert game.state.extras["checks_given"]["white"] == 3
    assert game.status() is GameStatus.VARIANT_WIN


def test_three_check_mate_remains_checkmate() -> None:
    mode = three_check_chess()
    state = mode.initial_state()
    _clear(
        state,
        {
            4: _piece("king", PieceSide.WHITE),
            3: _piece("rook", PieceSide.WHITE),
            62: _piece("king", PieceSide.BLACK),
            53: _piece("pawn", PieceSide.BLACK),
            54: _piece("pawn", PieceSide.BLACK),
            55: _piece("pawn", PieceSide.BLACK),
        },
        PieceSide.WHITE,
    )
    state.extras["castling_rights"] = set()
    game = LocalGameService(mode, initial_state=state)
    game.play(MoveAction(Square(3, 0), Square(3, 7)))
    assert game.status() is GameStatus.CHECKMATE
