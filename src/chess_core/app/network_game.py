"""Networked game service: local highlights, server-authoritative commits."""

from __future__ import annotations

from typing import Protocol

from chess_core.app.clock import ClockSnapshot
from chess_core.app.game import LocalGameService
from chess_core.app.game_record import TurnRecord
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.infra.network import GameServer
from chess_core.infra.network_messages import (
    StateEnvelope,
    UndoDecision,
    UndoPending,
    UndoResolved,
)
from chess_core.infra.tcp_client import TcpGameClient


class TurnTransport(Protocol):
    def submit_turn(self, turn: Turn, client_revision: int) -> None: ...

    def request_undo(self, *, plies: int = 1, base_revision: int = 0) -> None: ...

    def respond_undo(self, request_id: str, accept: bool) -> None: ...


class HostTurnTransport:
    def __init__(self, server: GameServer, session_id: str) -> None:
        self._server = server
        self._session_id = session_id

    def submit_turn(self, turn: Turn, client_revision: int) -> None:
        try:
            self._server.apply_remote_turn(
                self._session_id, turn, client_revision=client_revision
            )
        except PermissionError as exc:
            raise ValueError(str(exc)) from exc

    def request_undo(self, *, plies: int = 1, base_revision: int = 0) -> None:
        del base_revision
        self._server.request_undo(self._session_id, plies=plies)

    def respond_undo(self, request_id: str, accept: bool) -> None:
        self._server.respond_undo(
            UndoDecision(
                game_id=self._server.game_id,
                request_id=request_id,
                session_id=self._session_id,
                accept=accept,
            )
        )


class GuestTurnTransport:
    def __init__(self, client: TcpGameClient) -> None:
        self._client = client

    def submit_turn(self, turn: Turn, client_revision: int) -> None:
        self._client.submit_turn(turn, client_revision)

    def request_undo(self, *, plies: int = 1, base_revision: int = 0) -> None:
        self._client.request_undo(plies=plies, base_revision=base_revision)

    def respond_undo(self, request_id: str, accept: bool) -> None:
        self._client.respond_undo(request_id, accept)


class NetworkedLocalGameService(LocalGameService):
    """``LocalGameService`` whose completed turns are committed by the server."""

    def __init__(
        self,
        mode: GameMode,
        *,
        assigned_side: PieceSide,
        transport: TurnTransport,
        match_ready: bool = False,
    ) -> None:
        super().__init__(mode, allow_temporary_variations=False)
        self.assigned_side = assigned_side
        self._transport = transport
        self._match_ready = match_ready
        self._server_revision = 0
        self._undo_pending: UndoPending | None = None
        self.clock_snapshot: ClockSnapshot | None = None

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

    @property
    def can_play(self) -> bool:
        if not self._match_ready or self._undo_pending is not None:
            return False
        if self.state.side_to_move is not self.assigned_side:
            return False
        return super().can_play

    def can_undo(self) -> bool:
        if self._pending_actions:
            return True
        return (
            self._match_ready
            and self._record.live_revision > 0
            and self._undo_pending is None
        )

    def _apply_turn(self, turn: Turn) -> GameState:
        if not self._match_ready:
            raise ValueError("waiting for opponent")
        if turn.side is not self.assigned_side:
            raise ValueError("not your turn")
        self._transport.submit_turn(turn, self._server_revision)
        return self.state

    def undo(self) -> GameState:
        if self._pending_actions:
            self._pending_actions = []
            self._invalidate_caches()
            return self.state
        if not self.is_live:
            self._record.go_live()
        self._transport.request_undo(plies=1, base_revision=self._server_revision)
        return self.state

    def respond_undo(self, accept: bool) -> None:
        pending = self._undo_pending
        if pending is None:
            raise RuntimeError("no pending undo request")
        self._transport.respond_undo(pending.request_id, accept)

    def apply_server_message(self, message: object) -> None:
        if isinstance(message, StateEnvelope):
            self.apply_envelope(message)
            return
        if isinstance(message, UndoPending):
            self._undo_pending = message
            return
        if isinstance(message, UndoResolved):
            self._undo_pending = None
            if message.accepted and message.state is not None:
                envelope = StateEnvelope(
                    game_id=message.game_id,
                    revision=message.revision,
                    state=message.state,
                    last_turn=None,
                    clock=self.clock_snapshot,
                )
                self.apply_envelope(envelope)

    def apply_envelope(self, envelope: StateEnvelope) -> None:
        envelope.state.extras["mode"] = self.mode
        committed = int(envelope.state.extras.get("committed_turns") or 0)
        last_turn = envelope.last_turn
        if last_turn is not None and committed == self._record.turn_count + 1:
            before = self._record.live_state()
            after = envelope.state.clone(include_history=False)
            after.extras["mode"] = self.mode
            notation = self.mode.format_turn(
                last_turn, before=before, after=after
            )
            self._record.live_revision += 1
            self._record.view_revision = self._record.live_revision
            self._record.turns.append(
                TurnRecord(
                    last_turn,
                    self._record.live_revision,
                    notation,
                )
            )
            self._record._snapshots.append(after)
        else:
            while self._record.turn_count > committed:
                self._record.turns.pop()
                if len(self._record._snapshots) > 1:
                    self._record._snapshots.pop()
            self._record.live_revision = self._record.turn_count
            self._record.view_revision = self._record.live_revision
            snapshot = envelope.state.clone(include_history=False)
            snapshot.extras["mode"] = self.mode
            if self._record._snapshots:
                self._record._snapshots[-1] = snapshot
            else:
                self._record._snapshots = [snapshot]
            if committed == 0:
                self._record.initial = snapshot.clone(include_history=False)
                self._record.initial.extras["mode"] = self.mode
        self._server_revision = envelope.revision
        self._pending_actions = []
        if envelope.clock is not None:
            self.clock_snapshot = envelope.clock
        self._invalidate_caches()
