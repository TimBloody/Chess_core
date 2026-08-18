"""Tests for LocalGameService undo and load."""

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.piece import PieceSide
from chess_core.modes.chess import classic_chess


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
