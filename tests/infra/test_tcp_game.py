import asyncio

import pytest

from chess_core import __version__
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, Turn
from chess_core.core.piece import PieceSide
from chess_core.infra.network import GameServer
from chess_core.infra.network_messages import (
    PROTOCOL_VERSION,
    HelloPayload,
    StateEnvelope,
    SubmitTurnPayload,
    TurnRejectedPayload,
)
from chess_core.infra.tcp_client import HelloRejectedError, TcpGameClient
from chess_core.infra.tcp_server import TcpGameServer
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess


def _e2e4() -> Turn:
    return Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))])


def _wait_until(predicate, inbox: list, *, timeout: float = 2.0):
    async def _run() -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if predicate(inbox):
                return
            await asyncio.sleep(0.02)
        raise AssertionError("timed out waiting for network message")

    return _run()


def test_two_tcp_clients_play_and_reject_stolen_move() -> None:
    asyncio.run(_two_clients())


async def _two_clients() -> None:
    register_builtin_modes()
    mode = classic_chess()
    game = GameServer(mode.initial_state(), mode=mode)
    server = TcpGameServer(game, port=0)
    port = await server.start()
    white_inbox: list[object] = []
    black_inbox: list[object] = []
    white = TcpGameClient(white_inbox.append)
    black = TcpGameClient(black_inbox.append)
    try:
        await white.connect("127.0.0.1", port)
        await black.connect("127.0.0.1", port)
        await _wait_until(
            lambda box: any(
                isinstance(item, StateEnvelope) and item.revision == 0 for item in box
            ),
            black_inbox,
        )
        await white._send(SubmitTurnPayload(_e2e4(), 0))
        await _wait_until(
            lambda box: any(
                isinstance(item, StateEnvelope) and item.revision == 1 for item in box
            ),
            black_inbox,
        )
        assert game.state.side_to_move is PieceSide.BLACK
        await black._send(SubmitTurnPayload(_e2e4(), 1))
        await _wait_until(
            lambda box: any(isinstance(item, TurnRejectedPayload) for item in box),
            black_inbox,
        )
        rejected = next(
            item for item in black_inbox if isinstance(item, TurnRejectedPayload)
        )
        assert "other side" in rejected.reason or "side" in rejected.reason
    finally:
        await white.close()
        await black.close()
        await server.close()


def test_version_mismatch_is_rejected() -> None:
    asyncio.run(_version_mismatch())


async def _version_mismatch() -> None:
    register_builtin_modes()
    mode = classic_chess()
    game = GameServer(mode.initial_state(), mode=mode)
    server = TcpGameServer(game, port=0)
    port = await server.start()
    client = TcpGameClient(lambda _message: None)
    try:
        with pytest.raises(HelloRejectedError) as caught:
            await client.connect(
                "127.0.0.1",
                port,
                hello=HelloPayload(protocol=PROTOCOL_VERSION, package="9.9.9"),
            )
        assert caught.value.reason == "version_mismatch"
        with pytest.raises(HelloRejectedError) as protocol:
            other = TcpGameClient(lambda _message: None)
            await other.connect(
                "127.0.0.1",
                port,
                hello=HelloPayload(protocol=PROTOCOL_VERSION + 1, package=__version__),
            )
        assert protocol.value.reason == "protocol_mismatch"
    finally:
        await client.close()
        await server.close()


def test_third_tcp_client_gets_game_full() -> None:
    asyncio.run(_game_full())


async def _game_full() -> None:
    register_builtin_modes()
    mode = classic_chess()
    game = GameServer(mode.initial_state(), mode=mode)
    server = TcpGameServer(game, port=0)
    port = await server.start()
    first = TcpGameClient(lambda _message: None)
    second = TcpGameClient(lambda _message: None)
    third = TcpGameClient(lambda _message: None)
    try:
        await first.connect("127.0.0.1", port)
        await second.connect("127.0.0.1", port)
        with pytest.raises(HelloRejectedError) as caught:
            await third.connect("127.0.0.1", port)
        assert caught.value.reason == "game_full"
    finally:
        await first.close()
        await second.close()
        await third.close()
        await server.close()
