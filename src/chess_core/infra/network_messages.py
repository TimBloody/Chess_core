"""Transport-neutral network DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chess_core.app.clock import ClockSnapshot
from chess_core.core.move import Turn
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState

PROTOCOL_VERSION = 1
DEFAULT_GAME_PORT = 8765


class MessageKind(Enum):
    HELLO = auto()
    HELLO_OK = auto()
    HELLO_REJECTED = auto()
    STATE_SYNC = auto()
    SUBMIT_TURN = auto()
    TURN_REJECTED = auto()
    UNDO_REQUEST = auto()
    UNDO_PENDING = auto()
    UNDO_DECISION = auto()
    UNDO_RESOLVED = auto()
    CLOCK_SYNC = auto()
    OPPONENT_LEFT = auto()


@dataclass(frozen=True, slots=True)
class StateEnvelope:
    game_id: str
    revision: int
    state: GameState
    clock: ClockSnapshot | None = None
    last_turn: Turn | None = None


@dataclass(frozen=True, slots=True)
class SubmitTurnPayload:
    turn: Turn
    client_revision: int


@dataclass(frozen=True, slots=True)
class TurnRejectedPayload:
    reason: str
    expected_revision: int


@dataclass(frozen=True, slots=True)
class HelloPayload:
    protocol: int
    package: str


@dataclass(frozen=True, slots=True)
class HelloOkPayload:
    session_id: str
    side: PieceSide
    mode_id: str
    game_id: str
    protocol: int
    package: str


@dataclass(frozen=True, slots=True)
class HelloRejectedPayload:
    reason: str


@dataclass(frozen=True, slots=True)
class OpponentLeft:
    game_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class UndoRequest:
    game_id: str
    request_id: str
    session_id: str
    base_revision: int
    plies: int = 1


@dataclass(frozen=True, slots=True)
class UndoPending:
    game_id: str
    request_id: str
    requester_side: PieceSide
    plies: int


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
