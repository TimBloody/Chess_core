"""asyncio TCP server that seats remote clients on an in-memory GameServer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from chess_core import __version__
from chess_core.infra.network import GameServer, NetworkSession
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    PROTOCOL_VERSION,
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    MessageKind,
    SubmitTurnPayload,
    TurnRejectedPayload,
    UndoDecision,
    UndoRequest,
)
from chess_core.infra.tcp_protocol import (
    ProtocolError,
    encode_frame,
    message_from_payload,
    message_to_payload,
    read_frame,
)


class TcpGameServer:
    """Bind ``0.0.0.0`` and proxy JSON-line messages into ``GameServer``."""

    def __init__(
        self,
        game: GameServer,
        *,
        host: str = "0.0.0.0",
        port: int = DEFAULT_GAME_PORT,
        on_remote_event: Callable[[object], None] | None = None,
    ) -> None:
        self.game = game
        self.host = host
        self.port = port
        self.on_remote_event = on_remote_event
        self._server: asyncio.AbstractServer | None = None
        self._writers: dict[str, asyncio.StreamWriter] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._serving = asyncio.Event()
        game.add_observer(self._on_game_message)

    @property
    def bound_port(self) -> int:
        return self.port

    async def start(self) -> int:
        self._loop = asyncio.get_running_loop()
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        sockets = self._server.sockets or ()
        if sockets:
            self.port = int(sockets[0].getsockname()[1])
            self.game.host(self.port)
        self._serving.set()
        return self.port

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        server = self._server
        self._server = None
        for writer in list(self._writers.values()):
            writer.close()
        self._writers.clear()
        if server is not None:
            server.close()
            await server.wait_closed()

    def _on_game_message(self, session_id: str, message: object) -> None:
        writer = self._writers.get(session_id)
        loop = self._loop
        if writer is None or loop is None:
            return
        loop.call_soon_threadsafe(lambda: loop.create_task(self._write(writer, message)))

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session: NetworkSession | None = None
        try:
            kind, payload = await read_frame(reader)
            if kind is not MessageKind.HELLO:
                await self._write(writer, HelloRejectedPayload("bad_hello"))
                return
            hello = message_from_payload(kind, payload)
            if not isinstance(hello, HelloPayload):
                await self._write(writer, HelloRejectedPayload("bad_hello"))
                return
            rejected = _hello_rejection(hello, self.game)
            if rejected is not None:
                await self._write(writer, rejected)
                return
            session = self.game.connect_client()
            self._writers[session.session_id] = writer
            await self._write(
                writer,
                HelloOkPayload(
                    session_id=session.session_id,
                    side=session.side,
                    mode_id=self.game.mode_id,
                    game_id=self.game.game_id,
                    protocol=PROTOCOL_VERSION,
                    package=__version__,
                ),
            )
            await self._write(writer, self.game.envelope())
            if self.on_remote_event is not None:
                self.on_remote_event(session)
            await self._read_loop(reader, session)
        except (ConnectionError, ProtocolError, asyncio.IncompleteReadError):
            pass
        finally:
            if session is not None:
                self._writers.pop(session.session_id, None)
                self.game.disconnect_session(session.session_id)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def _read_loop(
        self, reader: asyncio.StreamReader, session: NetworkSession
    ) -> None:
        while True:
            kind, payload = await read_frame(reader)
            message = message_from_payload(kind, payload)
            await self._dispatch(session, message)

    async def _dispatch(self, session: NetworkSession, message: object) -> None:
        writer = self._writers.get(session.session_id)
        if writer is None:
            return
        if isinstance(message, SubmitTurnPayload):
            try:
                self.game.apply_remote_turn(
                    session.session_id,
                    message.turn,
                    client_revision=message.client_revision,
                )
            except PermissionError as exc:
                await self._write(
                    writer,
                    TurnRejectedPayload(str(exc), self.game.revision),
                )
            except ValueError as exc:
                await self._write(
                    writer,
                    TurnRejectedPayload(str(exc), self.game.revision),
                )
            return
        if isinstance(message, UndoRequest):
            try:
                self.game.request_undo(session.session_id, plies=message.plies)
            except (RuntimeError, ValueError, PermissionError) as exc:
                await self._write(
                    writer,
                    TurnRejectedPayload(str(exc), self.game.revision),
                )
            return
        if isinstance(message, UndoDecision):
            try:
                self.game.respond_undo(
                    UndoDecision(
                        game_id=self.game.game_id,
                        request_id=message.request_id,
                        session_id=session.session_id,
                        accept=message.accept,
                    )
                )
            except (RuntimeError, ValueError, PermissionError) as exc:
                await self._write(
                    writer,
                    TurnRejectedPayload(str(exc), self.game.revision),
                )

    async def _write(self, writer: asyncio.StreamWriter, message: object) -> None:
        try:
            kind, payload = message_to_payload(message)
            writer.write(encode_frame(kind, payload))
            await writer.drain()
        except (ConnectionError, ConnectionResetError, BrokenPipeError, ProtocolError):
            return


def _hello_rejection(hello: HelloPayload, game: GameServer) -> HelloRejectedPayload | None:
    if hello.protocol != PROTOCOL_VERSION:
        return HelloRejectedPayload("protocol_mismatch")
    if hello.package != __version__:
        return HelloRejectedPayload("version_mismatch")
    if game.seated >= 2:
        return HelloRejectedPayload("game_full")
    return None
