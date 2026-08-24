"""Async TCP adapter around GameServer."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from chess_core import __version__
from chess_core.app.match import match_kind_key
from chess_core.infra.network import GameServer, NetworkSession
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    PROTOCOL_VERSION,
    BrainSelectPayload,
    ClaimSeatPayload,
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    LeaveSeatPayload,
    StartMatchPayload,
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
    def __init__(
        self,
        game: GameServer,
        *,
        port: int = DEFAULT_GAME_PORT,
        on_remote_event: Callable[[object], None] | None = None,
        on_game_message: Callable[[str, object], None] | None = None,
        bind: str = "0.0.0.0",
    ) -> None:
        self.game = game
        self.port = port
        self.bind = bind
        self.on_remote_event = on_remote_event
        self.on_game_message = on_game_message
        self._server: asyncio.AbstractServer | None = None
        self._writers: dict[str, asyncio.StreamWriter] = {}

    @property
    def bound_port(self) -> int:
        if self._server is None:
            return self.port
        sockets = self._server.sockets or ()
        if not sockets:
            return self.port
        return int(sockets[0].getsockname()[1])

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, self.bind, self.port)
        self.game.host(self.bound_port)
        return self.bound_port

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        for writer in list(self._writers.values()):
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        session: NetworkSession | None = None
        try:
            kind, payload = await read_frame(reader)
            hello = message_from_payload(kind, payload)
            if not isinstance(hello, HelloPayload):
                await self._write_raw(writer, HelloRejectedPayload("bad_hello"))
                return
            rejected = _hello_rejection(hello, self.game)
            if rejected is not None:
                await self._write_raw(writer, rejected)
                return
            session = self.game.connect_client()
            self._writers[session.session_id] = writer
            mode_id = self.game.mode.id if self.game.mode is not None else "chess"
            await self._write_raw(
                writer,
                HelloOkPayload(
                    session_id=session.session_id,
                    seat=session.seat,
                    mode_id=mode_id,
                    game_id=self.game.game_id,
                    protocol=PROTOCOL_VERSION,
                    package=__version__,
                    is_host=False,
                    match_kind=match_kind_key(self.game.match.kind),
                    side=session.side,
                ),
            )
            await self._flush_session(session)
            if self.on_remote_event is not None:
                self.on_remote_event(session)
            await self._read_loop(reader, session)
        except (asyncio.IncompleteReadError, ConnectionResetError, ProtocolError, OSError):
            pass
        finally:
            if session is not None:
                self._writers.pop(session.session_id, None)

    async def _read_loop(
        self, reader: asyncio.StreamReader, session: NetworkSession
    ) -> None:
        while True:
            kind, payload = await read_frame(reader)
            message = message_from_payload(kind, payload, mode=self.game.mode)
            await self._dispatch(session, message)

    async def _dispatch(self, session: NetworkSession, message: object) -> None:
        try:
            if isinstance(message, SubmitTurnPayload):
                self.game.apply_remote_turn(
                    session.session_id, message.turn, board_id=message.board_id
                )
            elif isinstance(message, ClaimSeatPayload):
                self.game.claim_seat(session.session_id, message.seat)
            elif isinstance(message, LeaveSeatPayload):
                self.game.leave_seat(session.session_id)
            elif isinstance(message, StartMatchPayload):
                self.game.start_match(session.session_id)
            elif isinstance(message, BrainSelectPayload):
                self.game.brain_select(
                    session.session_id, message.piece_type, board_id=message.board_id
                )
            elif isinstance(message, UndoRequest):
                self.game.request_undo(
                    session.session_id, plies=message.plies, board_id=message.board_id
                )
            elif isinstance(message, UndoDecision):
                self.game.respond_undo(
                    UndoDecision(
                        game_id=self.game.game_id,
                        request_id=message.request_id,
                        session_id=session.session_id,
                        accept=message.accept,
                    )
                )
            else:
                return
        except (PermissionError, ValueError, RuntimeError) as exc:
            await self._write(
                session,
                TurnRejectedPayload(reason=str(exc), expected_revision=self.game.revision),
            )
            return
        if self.on_game_message is not None:
            self.on_game_message(session.session_id, message)
        await self._flush_all()

    async def flush(self) -> None:
        await self._flush_all()

    async def _flush_all(self) -> None:
        for session in self.game._sessions.values():
            if session.session_id in self._writers:
                await self._flush_session(session)
            elif self.on_game_message is not None:
                pending = list(session.inbox)
                session.inbox.clear()
                for message in pending:
                    self.on_game_message(session.session_id, message)

    async def _flush_session(self, session: NetworkSession) -> None:
        pending = list(session.inbox)
        session.inbox.clear()
        for message in pending:
            await self._write(session, message)

    async def _write(self, session: NetworkSession, message: object) -> None:
        writer = self._writers.get(session.session_id)
        if writer is None:
            session.inbox.append(message)
            return
        await self._write_raw(writer, message)

    async def _write_raw(self, writer: asyncio.StreamWriter, message: object) -> None:
        kind, payload = message_to_payload(message)
        writer.write(encode_frame(kind, payload))
        await writer.drain()


def _hello_rejection(hello: HelloPayload, game: GameServer) -> HelloRejectedPayload | None:
    if hello.protocol != PROTOCOL_VERSION:
        return HelloRejectedPayload("protocol_mismatch")
    if hello.package and hello.package.split(".")[0] != __version__.split(".")[0]:
        return HelloRejectedPayload("version_mismatch")
    try:
        if len(game._sessions) >= game._max_sessions:
            return HelloRejectedPayload("game_full")
    except AttributeError:
        return None
    return None
