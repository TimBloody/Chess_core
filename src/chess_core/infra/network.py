"""Transport-neutral messages and an in-memory game server with lobby seats."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from chess_core.app.clock import ClockSnapshot
from chess_core.app.match import MatchController, MatchKind, MatchPhase, seat_allows_undo_response
from chess_core.app.seats import SPECTATOR, spec_by_id
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.network_messages import (
    MAX_SESSIONS,
    BrainSelectPayload,
    LobbyOccupant,
    LobbyState,
    MatchEnvelope,
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


InboxMessage = (
    StateMessage
    | StateEnvelope
    | MatchEnvelope
    | LobbyState
    | UndoPending
    | UndoResolved
)


@dataclass
class NetworkSession:
    session_id: str
    side: PieceSide | None
    server: GameServer
    seat: str = SPECTATOR
    seats: set[str] = field(default_factory=set)
    is_bot: bool = False
    inbox: list[InboxMessage] = field(default_factory=list)

    def send_state(self, state: GameState) -> None:
        self.inbox.append(StateMessage(self.session_id, state.clone()))

    def send_turn(self, turn: Turn, board_id: str | None = None) -> None:
        self.server.apply_remote_turn(self.session_id, turn, board_id=board_id)

    def request_undo(self, plies: int = 1, board_id: str | None = None) -> UndoRequest:
        return self.server.request_undo(self.session_id, plies=plies, board_id=board_id)

    def respond_undo(self, request_id: str, accept: bool) -> UndoResolved:
        return self.server.respond_undo(
            UndoDecision(
                game_id=self.server.game_id,
                request_id=request_id,
                session_id=self.session_id,
                accept=accept,
            )
        )

    def claim_seat(self, seat: str) -> None:
        self.server.claim_seat(self.session_id, seat)

    def leave_seat(self) -> None:
        self.server.leave_seat(self.session_id)


@dataclass
class _PendingUndo:
    request: UndoRequest
    requester_seat: str
    requester_side: PieceSide
    board_id: str


class GameServer:
    """Authoritative server: lobby seats, match controller, legality, undo, clocks."""

    def __init__(
        self,
        initial_state: GameState,
        *,
        mode: GameMode | None = None,
        time_control: TimeControlConfig | None = None,
        game_id: str | None = None,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self.game_id = game_id or uuid4().hex
        self.port: int | None = None
        self.revision = 0
        self._max_sessions = max_sessions
        resolved_mode = mode or initial_state.extras.get("mode")
        self._mode = resolved_mode if isinstance(resolved_mode, GameMode) else None
        self._match = MatchController(
            self._mode or _fallback_mode(initial_state),
            initial_state,
            clock=_SystemClock(),
            time_control=time_control,
        )
        self._sessions: dict[str, NetworkSession] = {}
        self._host_session_id: str | None = None
        self._pending_undo: _PendingUndo | None = None
        self._kind_key = {
            MatchKind.SINGLE: "single",
            MatchKind.BUGHOUSE: "bughouse",
            MatchKind.HAND_AND_BRAIN: "hand_and_brain",
        }[self._match.kind]

    @property
    def state(self) -> GameState:
        return self._match.state.primary_state

    @property
    def match(self) -> MatchController:
        return self._match

    @property
    def mode(self) -> GameMode | None:
        return self._mode

    def host(self, port: int) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self.port = port

    def connect_client(self) -> NetworkSession:
        if len(self._sessions) >= self._max_sessions:
            raise ConnectionError("game is full")
        session = NetworkSession(uuid4().hex, None, self, SPECTATOR)
        self._sessions[session.session_id] = session
        if self._host_session_id is None:
            self._host_session_id = session.session_id
        if self._match.kind is MatchKind.SINGLE:
            self._auto_seat_single(session)
        self._broadcast_lobby()
        self._broadcast_all()
        return session

    def claim_seat(self, session_id: str, seat: str) -> None:
        session = self._require_session(session_id)
        if self._match.state.phase is not MatchPhase.LOBBY:
            raise PermissionError("cannot change seats after start")
        if seat == SPECTATOR:
            session.seat = SPECTATOR
            session.seats.clear()
            session.side = None
            self._broadcast_lobby()
            return
        spec = spec_by_id(self._kind_key, seat)
        if spec is None:
            raise ValueError(f"unknown seat: {seat}")
        occupant = self._occupant_of(seat)
        if occupant is not None and occupant.session_id != session_id:
            raise PermissionError("seat is occupied")
        if self._match.kind is MatchKind.BUGHOUSE:
            if seat in session.seats:
                session.seats.remove(seat)
                session.seat = next(iter(session.seats), SPECTATOR)
                current = spec_by_id(self._kind_key, session.seat)
                session.side = None if current is None else current.side
            else:
                session.seats.add(seat)
                session.seat = seat
                session.side = spec.side
            self._broadcast_lobby()
            return
        session.seats = {seat}
        session.seat = seat
        session.side = spec.side
        self._maybe_autostart_single()
        self._broadcast_lobby()

    def leave_seat(self, session_id: str) -> None:
        self.claim_seat(session_id, SPECTATOR)

    def start_match(self, session_id: str) -> None:
        session = self._require_session(session_id)
        if session.session_id != self._host_session_id:
            raise PermissionError("only the host can start the match")
        missing = self._empty_player_seats()
        if missing:
            raise PermissionError("not all player seats are filled")
        self._match.start()
        self.revision += 1
        self._broadcast_lobby()
        self._broadcast_all()

    def apply_remote_turn(
        self, session_id: str, turn: Turn, *, board_id: str | None = None
    ) -> GameState:
        if self._pending_undo is not None:
            raise PermissionError("cannot play while undo is pending")
        session = self._require_session(session_id)
        spec = self._spec_for_turn(session, turn, board_id)
        if spec is None:
            raise PermissionError("spectators cannot submit turns")
        if self._match.state.phase is MatchPhase.LOBBY:
            raise PermissionError("match has not started")
        self._match.apply_turn(spec, turn, board_id=board_id)
        self.revision += 1
        self._broadcast_all()
        return self.state.clone()

    def brain_select(self, session_id: str, piece_type: str, *, board_id: str | None = None) -> None:
        session = self._require_session(session_id)
        spec = self._spec_for_board(session, board_id)
        if spec is None:
            raise PermissionError("spectators cannot select a piece type")
        self._match.brain_select(spec, piece_type)
        self.revision += 1
        self._broadcast_all()

    def request_undo(
        self, session_id: str, *, plies: int = 1, board_id: str | None = None
    ) -> UndoRequest:
        if self._pending_undo is not None:
            raise RuntimeError("undo request already pending")
        session = self._require_session(session_id)
        spec = self._spec_for_board(session, board_id)
        if spec is None or session.side is None:
            raise PermissionError("spectators cannot request undo")
        target = board_id or spec.board_id
        if spec.board_id != target:
            raise PermissionError("cannot undo another board")
        if not self._match.can_undo_last_on(target):
            raise ValueError("not enough moves to undo")
        request = UndoRequest(
            game_id=self.game_id,
            request_id=uuid4().hex,
            session_id=session_id,
            base_revision=self.revision,
            plies=plies,
            board_id=target,
        )
        self._pending_undo = _PendingUndo(
            request=request,
            requester_seat=spec.seat_id,
            requester_side=spec.side,
            board_id=target,
        )
        pending = UndoPending(
            game_id=self.game_id,
            request_id=request.request_id,
            requester_side=session.side,
            plies=plies,
            board_id=target,
            requester_seat=spec.seat_id,
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
        requester = spec_by_id(self._kind_key, pending.requester_seat)
        responder = self._opponent_spec_for(session, requester)
        if requester is None or not seat_allows_undo_response(responder, requester):
            raise PermissionError("requester cannot accept own undo")
        if not decision.accept:
            self._pending_undo = None
            resolved = UndoResolved(
                game_id=self.game_id,
                request_id=pending.request.request_id,
                revision=self.revision,
                accepted=False,
                board_id=pending.board_id,
            )
            self._broadcast_resolved(resolved)
            return resolved
        if pending.request.base_revision != self.revision:
            raise ValueError("stale undo request")
        restored = self._match.undo_last_on(pending.board_id)
        self.revision += 1
        self._pending_undo = None
        resolved = UndoResolved(
            game_id=self.game_id,
            request_id=pending.request.request_id,
            revision=self.revision,
            accepted=True,
            state=restored,
            board_id=pending.board_id,
        )
        self._broadcast_resolved(resolved)
        return resolved

    def envelope(self) -> StateEnvelope:
        clocks = self._match.clock_snapshots()
        clock = clocks.get("main") or next(iter(clocks.values()), None)
        return StateEnvelope(
            game_id=self.game_id,
            revision=self.revision,
            state=self.state.clone(),
            clock=clock,
        )

    def match_envelope(self) -> MatchEnvelope:
        return MatchEnvelope(
            game_id=self.game_id,
            revision=self.revision,
            match_kind=self._match.kind,
            phase=self._match.state.phase,
            boards={board_id: board.clone() for board_id, board in self._match.state.boards.items()},
            clocks=self._match.clock_snapshots(),
            chosen_piece_type=self._match.state.chosen_piece_type,
            result=self._match.state.result,
            lobby=self.lobby_state(),
        )

    def lobby_state(self) -> LobbyState:
        occupants = tuple(
            LobbyOccupant(
                session_id=session.session_id,
                seat=seat,
                is_host=session.session_id == self._host_session_id,
                is_bot=session.is_bot,
            )
            for session in self._sessions.values()
            for seat in (session.seats or {session.seat})
        )
        return LobbyState(
            game_id=self.game_id,
            phase=self._match.state.phase,
            occupants=occupants,
            host_session_id=self._host_session_id or "",
            required_seats=tuple(spec.seat_id for spec in self._match.player_seats),
        )

    def _auto_seat_single(self, session: NetworkSession) -> None:
        for seat in ("white", "black"):
            if self._occupant_of(seat) is None:
                session.seat = seat
                session.seats = {seat}
                spec = spec_by_id("single", seat)
                session.side = None if spec is None else spec.side
                self._maybe_autostart_single()
                return

    def _maybe_autostart_single(self) -> None:
        if self._match.kind is not MatchKind.SINGLE:
            return
        if self._match.state.phase is not MatchPhase.LOBBY:
            return
        if self._empty_player_seats():
            return
        self._match.start()

    def _empty_player_seats(self) -> tuple[str, ...]:
        taken = {
            seat
            for session in self._sessions.values()
            for seat in (session.seats or {session.seat})
        }
        return tuple(
            spec.seat_id for spec in self._match.player_seats if spec.seat_id not in taken
        )

    def _occupant_of(self, seat: str) -> NetworkSession | None:
        for session in self._sessions.values():
            if seat in session.seats or session.seat == seat:
                return session
        return None

    def add_bot(self, seat: str) -> NetworkSession:
        """Create a server-local bot session occupying one free player seat."""
        if self._match.state.phase is not MatchPhase.LOBBY:
            raise PermissionError("cannot add bots after start")
        if self._occupant_of(seat) is not None:
            raise PermissionError("seat is occupied")
        spec = spec_by_id(self._kind_key, seat)
        if spec is None:
            raise ValueError(f"unknown seat: {seat}")
        session = NetworkSession(
            session_id=f"bot:{uuid4().hex}",
            side=spec.side,
            server=self,
            seat=seat,
            seats={seat},
            is_bot=True,
        )
        self._sessions[session.session_id] = session
        self._broadcast_lobby()
        return session

    def fill_empty_seats_with_bots(self) -> dict[str, str]:
        """Fill every unclaimed player seat and return seat -> bot session id."""
        result: dict[str, str] = {}
        for seat in self._empty_player_seats():
            bot = self.add_bot(seat)
            result[seat] = bot.session_id
        return result

    def _spec_for_turn(
        self, session: NetworkSession, turn: Turn, board_id: str | None
    ):
        target = board_id
        for seat in session.seats or {session.seat}:
            spec = spec_by_id(self._kind_key, seat)
            if spec is None:
                continue
            if target is not None and spec.board_id != target:
                continue
            if spec.side is turn.side:
                return spec
        return None

    def _spec_for_board(self, session: NetworkSession, board_id: str | None):
        for seat in session.seats or {session.seat}:
            spec = spec_by_id(self._kind_key, seat)
            if spec is not None and (board_id is None or spec.board_id == board_id):
                return spec
        return None

    def _opponent_spec_for(self, session: NetworkSession, requester):
        if requester is None:
            return None
        for seat in session.seats or {session.seat}:
            spec = spec_by_id(self._kind_key, seat)
            if seat_allows_undo_response(spec, requester):
                return spec
        return None

    def _require_session(self, session_id: str) -> NetworkSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise PermissionError("unknown network session") from exc

    def _broadcast_state(self, session: NetworkSession) -> None:
        session.inbox.append(self.envelope())
        session.inbox.append(self.match_envelope())

    def _broadcast_lobby(self) -> None:
        lobby = self.lobby_state()
        for connected in self._sessions.values():
            connected.inbox.append(lobby)

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

    def submit_turn(self, turn: Turn, board_id: str | None = None) -> None:
        if self.session is None:
            raise RuntimeError("client is not connected")
        self.session.send_turn(turn, board_id=board_id)


def _fallback_mode(state: GameState) -> GameMode:
    mode = state.extras.get("mode")
    if isinstance(mode, GameMode):
        return mode
    from chess_core.modes.chess import classic_chess

    return classic_chess()
