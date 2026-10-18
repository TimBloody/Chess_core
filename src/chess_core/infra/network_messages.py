"""Transport-neutral network DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chess_core.app.clock import ClockSnapshot
from chess_core.app.match import MatchKind, MatchPhase, MatchResult
from chess_core.core.move import Turn
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState

PROTOCOL_VERSION = 3
DEFAULT_GAME_PORT = 17474
MAX_SESSIONS = 8


class MessageKind(Enum):
    HELLO = auto()
    HELLO_OK = auto()
    HELLO_REJECTED = auto()
    STATE_SYNC = auto()
    MATCH_SYNC = auto()
    LOBBY_STATE = auto()
    CLAIM_SEAT = auto()
    LEAVE_SEAT = auto()
    START_MATCH = auto()
    BRAIN_SELECT = auto()
    SUBMIT_TURN = auto()
    TURN_REJECTED = auto()
    UNDO_REQUEST = auto()
    UNDO_PENDING = auto()
    UNDO_DECISION = auto()
    UNDO_RESOLVED = auto()
    CLOCK_SYNC = auto()


@dataclass(frozen=True, slots=True)
class HelloPayload:
    protocol: int
    package: str


@dataclass(frozen=True, slots=True)
class HelloOkPayload:
    session_id: str
    seat: str
    mode_id: str
    game_id: str
    protocol: int
    package: str
    is_host: bool
    match_kind: str
    side: PieceSide | None = None


@dataclass(frozen=True, slots=True)
class HelloRejectedPayload:
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimSeatPayload:
    seat: str


@dataclass(frozen=True, slots=True)
class LeaveSeatPayload:
    pass


@dataclass(frozen=True, slots=True)
class StartMatchPayload:
    pass


@dataclass(frozen=True, slots=True)
class BrainSelectPayload:
    piece_type: str
    board_id: str | None = None


@dataclass(frozen=True, slots=True)
class LobbyOccupant:
    session_id: str
    seat: str
    is_host: bool
    is_bot: bool = False


@dataclass(frozen=True, slots=True)
class LobbyState:
    game_id: str
    phase: MatchPhase
    occupants: tuple[LobbyOccupant, ...]
    host_session_id: str
    required_seats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StateEnvelope:
    game_id: str
    revision: int
    state: GameState
    clock: ClockSnapshot | None = None


@dataclass(frozen=True, slots=True)
class MatchEnvelope:
    game_id: str
    revision: int
    match_kind: MatchKind
    phase: MatchPhase
    boards: dict[str, GameState]
    clocks: dict[str, ClockSnapshot]
    chosen_piece_type: str | None = None
    result: MatchResult | None = None
    lobby: LobbyState | None = None


@dataclass(frozen=True, slots=True)
class SubmitTurnPayload:
    turn: Turn
    client_revision: int
    board_id: str | None = None


@dataclass(frozen=True, slots=True)
class TurnRejectedPayload:
    reason: str
    expected_revision: int


@dataclass(frozen=True, slots=True)
class UndoRequest:
    game_id: str
    request_id: str
    session_id: str
    base_revision: int
    plies: int = 1
    board_id: str | None = None


@dataclass(frozen=True, slots=True)
class UndoPending:
    game_id: str
    request_id: str
    requester_side: PieceSide
    plies: int
    board_id: str | None = None
    requester_seat: str | None = None


@dataclass(frozen=True, slots=True)
class UndoDecision:
    game_id: str
    request_id: str
    session_id: str
    accept: bool


@dataclass(frozen=True, slots=True)
class UndoResolved:
    game_id: str
    request_id: str
    revision: int
    accepted: bool
    state: GameState | None = None
    board_id: str | None = None
