"""Tests for confirmable undo protocol."""

from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.infra.network import GameClient, GameServer
from chess_core.infra.network_messages import UndoResolved
from chess_core.modes.chess import classic_chess


def test_undo_requires_opponent_confirmation() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    black = GameClient()
    white_session = white.connect(server)
    black_session = black.connect(server)
    white.submit_turn(Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]))
    request = white_session.request_undo()
    assert server.revision == 1
    resolved = black_session.respond_undo(request.request_id, accept=True)
    assert isinstance(resolved, UndoResolved)
    assert resolved.accepted
    assert server.state.board_state.piece_at(12) is not None


def test_undo_reject_keeps_position() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    black = GameClient()
    white_session = white.connect(server)
    black_session = black.connect(server)
    white.submit_turn(Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]))
    request = white_session.request_undo()
    resolved = black_session.respond_undo(request.request_id, accept=False)
    assert not resolved.accepted
    assert server.state.board_state.piece_at(28) is not None
