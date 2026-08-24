"""Application adapters for networked play."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from chess_core.app.game import LocalGameService
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.state import GameState
from chess_core.infra.network import GameServer
from chess_core.infra.network_messages import (
    MatchEnvelope as MatchEnvelopeDTO,
    StateEnvelope,
    UndoPending,
    UndoResolved,
)
from chess_core.infra.tcp_client import TcpGameClient


class TurnTransport(Protocol):
    def submit_turn(self, turn: Turn, client_revision: int, board_id: str | None = None) -> None: ...

    def request_undo(self, *, plies: int = 1, base_revision: int = 0, board_id: str | None = None) -> None: ...

    def respond_undo(self, request_id: str, accept: bool) -> None: ...

    def claim_seat(self, seat: str) -> None: ...

    def leave_seat(self) -> None: ...

    def start_match(self) -> None: ...

    def brain_select(self, piece_type: str, board_id: str | None = None) -> None: ...


class HostTurnTransport:
    def __init__(
        self,
        server: GameServer,
        session_id: str,
        *,
        on_flush: Callable[[], None] | None = None,
    ) -> None:
        self._server = server
        self._session_id = session_id
        self._on_flush = on_flush

    def submit_turn(self, turn: Turn, client_revision: int, board_id: str | None = None) -> None:
        del client_revision
        self._server.apply_remote_turn(self._session_id, turn, board_id=board_id)
        self._flush()

    def request_undo(self, *, plies: int = 1, base_revision: int = 0, board_id: str | None = None) -> None:
        del base_revision
        self._server.request_undo(self._session_id, plies=plies, board_id=board_id)
        self._flush()

    def respond_undo(self, request_id: str, accept: bool) -> None:
        from chess_core.infra.network_messages import UndoDecision

        self._server.respond_undo(
            UndoDecision(
                game_id=self._server.game_id,
                request_id=request_id,
                session_id=self._session_id,
                accept=accept,
            )
        )
        self._flush()

    def claim_seat(self, seat: str) -> None:
        self._server.claim_seat(self._session_id, seat)
        self._flush()

    def leave_seat(self) -> None:
        self._server.leave_seat(self._session_id)
        self._flush()

    def start_match(self) -> None:
        self._server.start_match(self._session_id)
        self._flush()

    def brain_select(self, piece_type: str, board_id: str | None = None) -> None:
        self._server.brain_select(self._session_id, piece_type, board_id=board_id)
        self._flush()

    def _flush(self) -> None:
        if self._on_flush is not None:
            self._on_flush()


class GuestTurnTransport:
    def __init__(self, client: TcpGameClient, *, schedule) -> None:
        self._client = client
        self._schedule = schedule

    def submit_turn(self, turn: Turn, client_revision: int, board_id: str | None = None) -> None:
        self._schedule(self._client.submit_turn(turn, client_revision, board_id))

    def request_undo(self, *, plies: int = 1, base_revision: int = 0, board_id: str | None = None) -> None:
        self._schedule(
            self._client.request_undo(plies=plies, base_revision=base_revision, board_id=board_id)
        )

    def respond_undo(self, request_id: str, accept: bool) -> None:
        self._schedule(self._client.respond_undo(request_id, accept))

    def claim_seat(self, seat: str) -> None:
        self._schedule(self._client.claim_seat(seat))

    def leave_seat(self) -> None:
        self._schedule(self._client.leave_seat())

    def start_match(self) -> None:
        self._schedule(self._client.start_match())

    def brain_select(self, piece_type: str, board_id: str | None = None) -> None:
        self._schedule(self._client.brain_select(piece_type, board_id))


class NetworkedLocalGameService(LocalGameService):
    """LocalGameService that submits turns through a network transport."""

    def __init__(
        self,
        mode: GameMode,
        transport: TurnTransport,
        initial_state: GameState | None = None,
        *,
        match_ready: bool = False,
        board_id: str = "main",
    ) -> None:
        super().__init__(mode, initial_state)
        self._transport = transport
        self._match_ready = match_ready
        self._server_revision = 0
        self._undo_pending: UndoPending | None = None
        self.board_id = board_id
        self.chosen_piece_type: str | None = None

    @property
    def match_ready(self) -> bool:
        return self._match_ready

    @property
    def server_revision(self) -> int:
        return self._server_revision

    @property
    def pending_undo(self) -> UndoPending | None:
        return self._undo_pending

    def set_match_ready(self, ready: bool) -> None:
        self._match_ready = ready

    def can_play(self) -> bool:
        if not self._match_ready or self._undo_pending is not None:
            return False
        return super().is_live

    def can_undo(self) -> bool:
        return (
            self._match_ready
            and self._undo_pending is None
            and super().can_undo()
        )

    def _apply_turn(self, turn: Turn) -> GameState:
        if not self._match_ready:
            raise PermissionError("match is not ready")
        self._transport.submit_turn(turn, self._server_revision, self.board_id)
        return self.state

    def undo(self) -> GameState:
        if not self.can_undo():
            return self.state
        self._transport.request_undo(base_revision=self._server_revision, board_id=self.board_id)
        return self.state

    def respond_undo(self, accept: bool) -> None:
        pending = self._undo_pending
        if pending is None:
            return
        self._transport.respond_undo(pending.request_id, accept)

    def apply_server_message(self, message: object) -> None:
        if isinstance(message, StateEnvelope):
            self.apply_envelope(message)
        elif isinstance(message, MatchEnvelopeDTO):
            self.apply_match_envelope(message)
        elif isinstance(message, UndoPending):
            self._undo_pending = message
        elif isinstance(message, UndoResolved):
            self._undo_pending = None
            self._server_revision = message.revision
            if message.accepted and message.state is not None:
                self.load_position(message.state)

    def apply_envelope(self, envelope: StateEnvelope) -> None:
        self._server_revision = envelope.revision
        self.load_position(envelope.state)

    def apply_match_envelope(self, envelope: MatchEnvelopeDTO) -> None:
        self._server_revision = envelope.revision
        self.chosen_piece_type = envelope.chosen_piece_type
        board = envelope.boards.get(self.board_id)
        if board is None and envelope.boards:
            board = next(iter(envelope.boards.values()))
        if board is not None:
            self.load_position(board)
        from chess_core.app.match import MatchPhase

        self._match_ready = envelope.phase is MatchPhase.PLAYING
