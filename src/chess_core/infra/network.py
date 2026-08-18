"""Transport-neutral messages and an in-memory two-client game server."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from chess_core.app.clock import ClockSnapshot, GameClockService
from chess_core.core.gamemode import GameMode
from chess_core.core.move import MoveAction, Turn
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.network_messages import (
    StateEnvelope,
    UndoDecision,
    UndoPending,
    UndoRequest,
    UndoResolved,
)


@dataclass(frozen=True, slots=True)
class StateMessage:
    session_id: str
    state: GameState


@dataclass(frozen=True, slots=True)
class TurnMessage:
    session_id: str
    turn: Turn


class _SystemClock:
    import time

    def now_ms(self) -> int:
        return int(self.time.monotonic() * 1000)


@dataclass
class NetworkSession:
    session_id: str
    side: PieceSide
    server: GameServer
    inbox: list[StateMessage | StateEnvelope | UndoPending | UndoResolved] = field(
        default_factory=list
    )

    def send_state(self, state: GameState) -> None:
        self.inbox.append(StateMessage(self.session_id, state.clone()))

    def send_turn(self, turn: Turn) -> None:
        self.server.apply_remote_turn(self.session_id, turn)

    def request_undo(self, plies: int = 1) -> UndoRequest:
        return self.server.request_undo(self.session_id, plies=plies)

    def respond_undo(self, request_id: str, accept: bool) -> UndoResolved:
        return self.server.respond_undo(
            UndoDecision(
                game_id=self.server.game_id,
                request_id=request_id,
                session_id=self.session_id,
                accept=accept,
            )
        )


@dataclass
class _PendingUndo:
    request: UndoRequest
    requester_side: PieceSide


class GameServer:
    """Deterministic mock server with revision, legality, undo, and clocks."""

    def __init__(
        self,
        initial_state: GameState,
        *,
        mode: GameMode | None = None,
        time_control: TimeControlConfig | None = None,
        game_id: str | None = None,
    ) -> None:
        self.game_id = game_id or uuid4().hex
        self.state = initial_state.clone()
        self.revision = 0
        self.port: int | None = None
        self._sessions: dict[str, NetworkSession] = {}
        self._snapshots: list[GameState] = [self.state.clone(include_history=False)]
        self._turn_started_ms = _SystemClock().now_ms()
        self._pending_undo: _PendingUndo | None = None
        resolved_mode = mode or self.state.extras.get("mode")
        self._generator = MoveGenerator(resolved_mode) if resolved_mode is not None else None
        self._clock = (
            GameClockService(time_control, _SystemClock(), revision=0)
            if time_control is not None
            else None
        )

    def host(self, port: int) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self.port = port

    def connect_client(self) -> NetworkSession:
        if len(self._sessions) >= 2:
            raise ConnectionError("game already has two clients")
        side = PieceSide.WHITE if not self._sessions else PieceSide.BLACK
        session = NetworkSession(uuid4().hex, side, self)
        self._sessions[session.session_id] = session
        self._broadcast_state(session)
        return session

    def apply_remote_turn(self, session_id: str, turn: Turn) -> GameState:
        if self._pending_undo is not None:
            raise PermissionError("cannot play while undo is pending")
        session = self._require_session(session_id)
        if turn.side is not session.side:
            raise PermissionError("client cannot submit the other side's turn")
        if turn.side is not self.state.side_to_move:
            raise ValueError("turn side does not match position")
        self._validate_turn(turn)
        clock = _SystemClock()
        think_ms = max(0, clock.now_ms() - self._turn_started_ms)
        self.state = self.state.apply_turn(turn)
        self.revision += 1
        self._snapshots.append(self.state.clone(include_history=False))
        if self._clock is not None:
            self._clock.on_move_committed(turn.side, think_ms)
        self._turn_started_ms = clock.now_ms()
        self._broadcast_all()
        return self.state.clone()

    def request_undo(self, session_id: str, *, plies: int = 1) -> UndoRequest:
        if self._pending_undo is not None:
            raise RuntimeError("undo request already pending")
        if self.revision < plies:
            raise ValueError("not enough moves to undo")
        session = self._require_session(session_id)
        request = UndoRequest(
            game_id=self.game_id,
            request_id=uuid4().hex,
            session_id=session_id,
            base_revision=self.revision,
            plies=plies,
        )
        self._pending_undo = _PendingUndo(request=request, requester_side=session.side)
        pending = UndoPending(
            game_id=self.game_id,
            request_id=request.request_id,
            requester_side=session.side,
            plies=plies,
        )
        for connected in self._sessions.values():
            connected.inbox.append(pending)
        return request

    def respond_undo(self, decision: UndoDecision) -> UndoResolved:
        if self._pending_undo is None:
            raise RuntimeError("no pending undo request")
        pending = self._pending_undo
        if decision.request_id != pending.request.request_id:
            raise ValueError("unknown undo request")
        session = self._require_session(decision.session_id)
        if session.side is pending.requester_side:
            raise PermissionError("requester cannot accept own undo")
        if not decision.accept:
            self._pending_undo = None
            resolved = UndoResolved(
                game_id=self.game_id,
                request_id=pending.request.request_id,
                revision=self.revision,
                accepted=False,
            )
            self._broadcast_resolved(resolved)
            return resolved
        if pending.request.base_revision != self.revision:
            raise ValueError("stale undo request")
        for _ in range(pending.request.plies):
            if len(self._snapshots) <= 1:
                break
            self._snapshots.pop()
        self.state = self._snapshots[-1].clone()
        self.revision += 1
        if self._clock is not None:
            self._clock.on_undo()
        self._pending_undo = None
        resolved = UndoResolved(
            game_id=self.game_id,
            request_id=pending.request.request_id,
            revision=self.revision,
            accepted=True,
            state=self.state.clone(),
        )
        self._broadcast_resolved(resolved)
        return resolved

    def envelope(self) -> StateEnvelope:
        clock = self._clock.snapshot() if self._clock is not None else None
        return StateEnvelope(
            game_id=self.game_id,
            revision=self.revision,
            state=self.state.clone(),
            clock=clock,
        )

    def _validate_turn(self, turn: Turn) -> None:
        if self._generator is None:
            return
        legal = self._generator.generate_legal(self.state)
        if not turn.actions:
            raise ValueError("turn has no actions")
        first = turn.actions[0]
        if isinstance(first, MoveAction) and first not in legal:
            raise ValueError("turn is not legal")

    def _require_session(self, session_id: str) -> NetworkSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise PermissionError("unknown network session") from exc

    def _broadcast_state(self, session: NetworkSession) -> None:
        session.inbox.append(self.envelope())

    def _broadcast_all(self) -> None:
        for connected in self._sessions.values():
            self._broadcast_state(connected)

    def _broadcast_resolved(self, resolved: UndoResolved) -> None:
        for connected in self._sessions.values():
            connected.inbox.append(resolved)
            if resolved.accepted:
                self._broadcast_state(connected)


class GameClient:
    def __init__(self) -> None:
        self.session: NetworkSession | None = None

    def connect(self, server: GameServer) -> NetworkSession:
        self.session = server.connect_client()
        return self.session

    def submit_turn(self, turn: Turn) -> None:
        if self.session is None:
            raise RuntimeError("client is not connected")
        self.session.send_turn(turn)
