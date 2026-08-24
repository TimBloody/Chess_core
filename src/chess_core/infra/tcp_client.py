"""Async TCP game client."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from chess_core.core.gamemode import GameMode
from chess_core.infra.network_messages import (
    BrainSelectPayload,
    ClaimSeatPayload,
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    LeaveSeatPayload,
    StartMatchPayload,
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
from chess_core.core.move import Turn


class HelloRejectedError(ConnectionError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TcpGameClient:
    def __init__(
        self,
        *,
        on_message: Callable[[object], None] | None = None,
        mode_resolver: Callable[[str], GameMode] | None = None,
    ) -> None:
        self.on_message = on_message
        self.hello: HelloOkPayload | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._mode: GameMode | None = None
        self._mode_resolver = mode_resolver
        self._task: asyncio.Task[None] | None = None

    async def connect(
        self,
        host: str,
        port: int,
        *,
        hello: HelloPayload | None = None,
        mode: GameMode | None = None,
    ) -> HelloOkPayload:
        self._mode = mode
        self._reader, self._writer = await asyncio.open_connection(host, port)
        await self._send(hello or local_hello())
        kind, payload = await read_frame(self._reader)
        message = message_from_payload(kind, payload, mode=mode)
        if isinstance(message, HelloRejectedPayload):
            await self.close()
            raise HelloRejectedError(message.reason)
        if not isinstance(message, HelloOkPayload):
            await self.close()
            raise ProtocolError("expected HELLO_OK")
        self.hello = message
        if self._mode is None and self._mode_resolver is not None:
            self._mode = self._mode_resolver(message.mode_id)
        self._task = asyncio.create_task(self._read_loop())
        if self.on_message is not None:
            self.on_message(message)
        return message

    async def submit_turn(self, turn: Turn, client_revision: int, board_id: str | None = None) -> None:
        await self._send(SubmitTurnPayload(turn, client_revision, board_id))

    async def claim_seat(self, seat: str) -> None:
        await self._send(ClaimSeatPayload(seat))

    async def leave_seat(self) -> None:
        await self._send(LeaveSeatPayload())

    async def start_match(self) -> None:
        await self._send(StartMatchPayload())

    async def brain_select(self, piece_type: str, board_id: str | None = None) -> None:
        await self._send(BrainSelectPayload(piece_type, board_id))

    async def request_undo(self, *, plies: int = 1, base_revision: int = 0, board_id: str | None = None) -> None:
        hello = self.hello
        if hello is None:
            raise RuntimeError("client is not connected")
        await self._send(
            UndoRequest(
                game_id=hello.game_id,
                request_id="",
                session_id=hello.session_id,
                base_revision=base_revision,
                plies=plies,
                board_id=board_id,
            )
        )

    async def respond_undo(self, request_id: str, accept: bool) -> None:
        hello = self.hello
        if hello is None:
            raise RuntimeError("client is not connected")
        await self._send(
            UndoDecision(
                game_id=hello.game_id,
                request_id=request_id,
                session_id=hello.session_id,
                accept=accept,
            )
        )

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._writer = None
        self._reader = None

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                kind, payload = await read_frame(self._reader)
                message = message_from_payload(kind, payload, mode=self._mode)
                if self.on_message is not None:
                    self.on_message(message)
        except (asyncio.IncompleteReadError, ConnectionResetError, ProtocolError, OSError):
            return

    async def _send(self, message: object) -> None:
        if self._writer is None:
            raise RuntimeError("client is not connected")
        kind, payload = message_to_payload(message)
        self._writer.write(encode_frame(kind, payload))
        await self._writer.drain()
