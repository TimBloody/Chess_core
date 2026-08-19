import pytest

from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.infra.network import GameClient, GameServer
from chess_core.modes.chess import classic_chess, duck_chess


def _e2e4() -> Turn:
    return Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])


def _e7e5() -> Turn:
    return Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))])


def test_rejects_other_side_and_wrong_turn() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    black = GameClient()
    white.connect(server)
    black.connect(server)
    with pytest.raises(PermissionError, match="other side"):
        white.submit_turn(_e7e5())
    with pytest.raises(ValueError, match="side"):
        black.submit_turn(_e7e5())


def test_rejects_stale_revision() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    black = GameClient()
    white.connect(server)
    black.connect(server)
    white.submit_turn(_e2e4(), client_revision=0)
    assert server.revision == 1
    with pytest.raises(ValueError, match="stale revision"):
        black.submit_turn(_e7e5(), client_revision=0)
    black.submit_turn(_e7e5(), client_revision=1)
    assert server.state.side_to_move is PieceSide.WHITE


def test_rejects_illegal_move() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    white.connect(server)
    GameClient().connect(server)
    illegal = Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 4))])
    with pytest.raises(ValueError, match="not legal"):
        white.submit_turn(illegal, client_revision=0)


def test_rejects_incomplete_duck_turn() -> None:
    mode = duck_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    white.connect(server)
    GameClient().connect(server)
    with pytest.raises(ValueError, match="not legal"):
        white.submit_turn(_e2e4(), client_revision=0)


def test_third_client_is_rejected() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    GameClient().connect(server)
    GameClient().connect(server)
    with pytest.raises(ConnectionError, match="two clients"):
        GameClient().connect(server)
