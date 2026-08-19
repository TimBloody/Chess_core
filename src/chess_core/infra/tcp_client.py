"""asyncio TCP client for the LAN game protocol."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from chess_core.core.move import Turn
from chess_core.infra.network_messages import (
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    SubmitTurnPayload,
    UndoDecision,
    UndoRequest,
)
from chess_core.infra.tcp_protocol import (
    ProtocolError,
    encode_frame,
    local_hello,
    message_from_payload,
    message_to_payload,
    read_frame,
)


class HelloRejectedError(ConnectionError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TcpGameClient:
    """Connect, handshake, then deliver server messages to ``on_message``."""

    def __init__(self, on_message: Callable[[object], None]) -> None:
        self.on_message = on_message
        self.hello: HelloOkPayload | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def session_id(self) -> str:
        if self.hello is None:
            raise RuntimeError("client is not connected")
        return self.hello.session_id

    async def connect(
        self,
        host: str,
        port: int,
        *,
        hello: HelloPayload | None = None,
    ) -> HelloOkPayload:
        reader, writer = await asyncio.open_connection(host, port)
        self._reader = reader
        self._writer = writer
        self._loop = asyncio.get_running_loop()
        await self._send(hello or local_hello())
        kind, payload = await read_frame(reader)
        message = message_from_payload(kind, payload)
        if isinstance(message, HelloRejectedPayload):
            await self.close()
            raise HelloRejectedError(message.reason)
        if not isinstance(message, HelloOkPayload):
            await self.close()
            raise ProtocolError("expected HELLO_OK")
        self.hello = message
        self.on_message(message)
        self._reader_task = asyncio.create_task(self._read_loop())
        return message

    def submit_turn(self, turn: Turn, client_revision: int) -> None:
        self.send_threadsafe(SubmitTurnPayload(turn, client_revision))

    def request_undo(self, *, plies: int = 1, base_revision: int = 0) -> None:
        hello = self.hello
        if hello is None:
            raise RuntimeError("client is not connected")
        self.send_threadsafe(
            UndoRequest(
                game_id=hello.game_id,
                request_id="",
                session_id=hello.session_id,
                base_revision=base_revision,
                plies=plies,
            )
        )

    def respond_undo(self, request_id: str, accept: bool) -> None:
        hello = self.hello
        if hello is None:
            raise RuntimeError("client is not connected")
        self.send_threadsafe(
            UndoDecision(
                game_id=hello.game_id,
                request_id=request_id,
                session_id=hello.session_id,
                accept=accept,
            )
        )

    def send_threadsafe(self, message: object) -> None:
        loop = self._loop
        if loop is None:
            raise RuntimeError("client is not connected")
        asyncio.run_coroutine_threadsafe(self._send(message), loop)

    async def close(self) -> None:
        task = self._reader_task
        self._reader_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, ConnectionError, ProtocolError):
                pass
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def _read_loop(self) -> None:
        reader = self._reader
        if reader is None:
            return
        try:
            while True:
                kind, payload = await read_frame(reader)
                self.on_message(message_from_payload(kind, payload))
        except (ConnectionError, ProtocolError, asyncio.IncompleteReadError):
            return

    async def _send(self, message: object) -> None:
        writer = self._writer
        if writer is None:
            raise RuntimeError("client is not connected")
        kind, payload = message_to_payload(message)
        writer.write(encode_frame(kind, payload))
        await writer.drain()
