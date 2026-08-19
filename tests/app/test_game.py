"""Tests for LocalGameService undo and load."""

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import DropAction, MoveAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import HandsState
from chess_core.modes.chess import classic_chess, crazyhouse


def test_undo_restores_previous_position() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    assert game.state.side_to_move is PieceSide.BLACK
    game.undo()
    assert game.state.side_to_move is PieceSide.WHITE
    assert game.state.board_state.piece_at(12) is not None


def test_load_position_resets_history() -> None:
    game = LocalGameService(classic_chess())
    game.play(MoveAction(Square(4, 1), Square(4, 3)))
    loaded = classic_chess().initial_state()
    game.load_position(loaded)
    assert game.record.live_revision == 0
    assert game.can_undo() is False


def test_select_hand_piece_lists_drop_squares_and_toggles_off() -> None:
    mode = crazyhouse()
    state = mode.initial_state()
    for index in range(64):
        state.board_state.cells[index] = None
    state.board_state.cells[4] = Piece(PieceTypeId("king"), PieceSide.WHITE)
    state.board_state.cells[60] = Piece(PieceTypeId("king"), PieceSide.BLACK)
    state.hands = HandsState(
        {PieceSide.WHITE: [Piece(PieceTypeId("knight"), PieceSide.WHITE)]}
    )
    game = LocalGameService(mode, initial_state=state)
    drops = game.select_hand_piece("knight")
    assert game.selected_hand_type == "knight"
    assert DropAction(PieceTypeId("knight"), Square(0, 0)) in drops
    game.play_selected_drop(Square(3, 3))
    assert game.state.board_state.piece_at(27).piece_type.name == "knight"
    assert game.selected_hand_type is None


def test_temporary_variation_restores_imported_mainline() -> None:
    game = LocalGameService(
        classic_chess(),
        allow_temporary_variations=True,
    )
    game.play(MoveAction(Square(4, 1), Square(4, 3)))  # e4
    game.play(MoveAction(Square(4, 6), Square(4, 4)))  # e5
    game.go_to_revision(1)

    assert game.can_play
    game.play(MoveAction(Square(2, 6), Square(2, 4)))  # c5
    assert game.in_variation
    assert game.state.board_state.piece_at(34).piece_type.name == "pawn"
    assert game.state.board_state.piece_at(36) is None

    game.return_to_mainline()
    assert not game.in_variation
    assert game.is_live
    assert game.state.board_state.piece_at(36).piece_type.name == "pawn"
    assert game.state.board_state.piece_at(34) is None
