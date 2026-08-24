"""Lobby seats and four-client match permissions."""

import pytest

from chess_core.app.seats import SPECTATOR
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.infra.network import GameClient, GameServer
from chess_core.modes.bughouse import bughouse
from chess_core.modes.chess import classic_chess
from chess_core.modes.hand_and_brain import hand_and_brain


def test_fifth_client_is_spectator() -> None:
    mode = bughouse()
    server = GameServer(mode.initial_state(), mode=mode)
    sessions = [GameClient().connect(server) for _ in range(5)]
    assert sessions[-1].seat == SPECTATOR
    assert sessions[-1].side is None


def test_claim_and_leave_before_start() -> None:
    mode = bughouse()
    server = GameServer(mode.initial_state(), mode=mode)
    first = GameClient().connect(server)
    first.claim_seat("a_white")
    assert first.seat == "a_white"
    first.leave_seat()
    assert first.seat == SPECTATOR
    first.claim_seat("b_black")
    assert first.seat == "b_black"


def test_start_requires_four_players() -> None:
    mode = bughouse()
    server = GameServer(mode.initial_state(), mode=mode)
    host = GameClient().connect(server)
    with pytest.raises(PermissionError):
        server.start_match(host.session_id)
    seats = ("a_white", "a_black", "b_white", "b_black")
    players = [host]
    host.claim_seat(seats[0])
    for seat in seats[1:]:
        client = GameClient().connect(server)
        client.claim_seat(seat)
        players.append(client)
    server.start_match(host.session_id)
    assert server.match.state.phase.name == "PLAYING"


def test_wrong_board_or_brain_cannot_move() -> None:
    mode = bughouse()
    server = GameServer(mode.initial_state(), mode=mode)
    host = GameClient().connect(server)
    seats = ("a_white", "a_black", "b_white", "b_black")
    host.claim_seat(seats[0])
    others = []
    for seat in seats[1:]:
        client = GameClient().connect(server)
        client.claim_seat(seat)
        others.append(client)
    server.start_match(host.session_id)
    with pytest.raises(PermissionError):
        server.apply_remote_turn(
            others[0].session_id,
            Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
            board_id="A",
        )


def test_hand_brain_brain_cannot_submit_turn() -> None:
    mode = hand_and_brain()
    server = GameServer(mode.initial_state(), mode=mode)
    host = GameClient().connect(server)
    for seat, client in (
        ("white_brain", host),
        ("white_hand", GameClient().connect(server)),
        ("black_brain", GameClient().connect(server)),
        ("black_hand", GameClient().connect(server)),
    ):
        client.claim_seat(seat)
    host.claim_seat("white_brain")
    server.start_match(host.session_id)
    with pytest.raises(PermissionError):
        server.apply_remote_turn(
            host.session_id,
            Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]),
        )


def test_classic_two_clients_still_auto_start() -> None:
    mode = classic_chess()
    server = GameServer(mode.initial_state(), mode=mode)
    white = GameClient()
    black = GameClient()
    white.connect(server)
    black.connect(server)
    white.submit_turn(Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]))
    assert server.state.side_to_move is PieceSide.BLACK
