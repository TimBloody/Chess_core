"""Tests for legal turn options and LocalGameService delegation."""

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.app.legal_turns import build_legal_turn_options
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.notation import NotationStyle
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes.chess import classic_chess


def test_legal_turn_options_group_by_source() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turns = mode.legal_turns(state)
    options = build_legal_turn_options(
        mode, state, turns, notation_style=NotationStyle.PIECE_SQUARE
    )
    assert options.options
    by_source = options.by_source()
    assert 12 in by_source
    assert all(option.source_square == 12 for option in by_source[12])


def test_play_turn_validates_through_mode_strategy() -> None:
    game = LocalGameService(classic_chess())
    turn = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])
    assert turn in [candidate for candidate in game.legal_turns()]
    game.play_turn(turn)
    assert game.state.side_to_move is PieceSide.BLACK


def test_play_turn_rejects_illegal_turn() -> None:
    game = LocalGameService(classic_chess())
    turn = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 4))])
    try:
        game.play_turn(turn)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_status_still_reports_checkmate_via_outcome() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    for index in range(mode.board.shape.cell_count):
        state.board_state.cells[index] = None
    state.board_state.cells[4] = Piece(PieceTypeId("king"), PieceSide.WHITE)
    state.board_state.cells[12] = Piece(PieceTypeId("queen"), PieceSide.BLACK)
    state.board_state.cells[20] = Piece(PieceTypeId("king"), PieceSide.BLACK)
    state.side_to_move = PieceSide.WHITE

    game = LocalGameService(mode, state)
    assert game.status() is GameStatus.CHECKMATE


def test_legal_moves_api_remains_compatible() -> None:
    game = LocalGameService(classic_chess())
    moves = game.legal_moves()
    assert moves
    game.play(moves[0])
    assert game.can_undo()
