"""Length-prefixed JSON frames for LAN play."""

from __future__ import annotations

import json
from typing import Any

from chess_core import __version__
from chess_core.app.clock import ClockSnapshot
from chess_core.app.match import MatchKind, MatchPhase, MatchResult
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig, TimeControlKind
from chess_core.infra.network_codec import (
    NetworkCodecError,
    decode_state,
    decode_turn,
    encode_state,
    encode_turn,
)
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    PROTOCOL_VERSION,
    BrainSelectPayload,
    ClaimSeatPayload,
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    LeaveSeatPayload,
    LobbyOccupant,
    LobbyState,
    MatchEnvelope,
    MessageKind,
    StartMatchPayload,
    StateEnvelope,
    SubmitTurnPayload,
    TurnRejectedPayload,
    UndoDecision,
    UndoPending,
    UndoRequest,
    UndoResolved,
)

__all__ = [
    "DEFAULT_GAME_PORT",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_frame",
    "encode_frame",
    "local_hello",
    "message_from_payload",
    "message_to_payload",
    "read_frame",
]

_HEADER_SIZE = 4


class ProtocolError(ValueError):
    pass


def encode_frame(kind: MessageKind, payload: dict[str, Any]) -> bytes:
    body = json.dumps({"kind": kind.name, "payload": payload}, separators=(",", ":")).encode("utf-8")
    return len(body).to_bytes(_HEADER_SIZE, "big") + body


async def read_frame(reader: object) -> tuple[MessageKind, dict[str, Any]]:
    header = await reader.readexactly(_HEADER_SIZE)  # type: ignore[attr-defined]
    length = int.from_bytes(header, "big")
    if length <= 0 or length > 4_000_000:
        raise ProtocolError("invalid frame length")
    raw = await reader.readexactly(length)  # type: ignore[attr-defined]
    return decode_frame(raw)


def decode_frame(raw: bytes) -> tuple[MessageKind, dict[str, Any]]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid JSON frame") from exc
    if not isinstance(data, dict):
        raise ProtocolError("frame must be an object")
    try:
        kind = MessageKind[str(data["kind"])]
    except KeyError as exc:
        raise ProtocolError("unknown message kind") from exc
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    return kind, payload


def message_to_payload(message: object) -> tuple[MessageKind, dict[str, Any]]:
    if isinstance(message, HelloPayload):
        return MessageKind.HELLO, {"protocol": message.protocol, "package": message.package}
    if isinstance(message, HelloOkPayload):
        return MessageKind.HELLO_OK, {
            "session_id": message.session_id,
            "seat": message.seat,
            "side": None if message.side is None else message.side.name,
            "mode_id": message.mode_id,
            "game_id": message.game_id,
            "protocol": message.protocol,
            "package": message.package,
            "is_host": message.is_host,
            "match_kind": message.match_kind,
        }
    if isinstance(message, HelloRejectedPayload):
        return MessageKind.HELLO_REJECTED, {"reason": message.reason}
    if isinstance(message, ClaimSeatPayload):
        return MessageKind.CLAIM_SEAT, {"seat": message.seat}
    if isinstance(message, LeaveSeatPayload):
        return MessageKind.LEAVE_SEAT, {}
    if isinstance(message, StartMatchPayload):
        return MessageKind.START_MATCH, {}
    if isinstance(message, BrainSelectPayload):
        return MessageKind.BRAIN_SELECT, {
            "piece_type": message.piece_type,
            "board_id": message.board_id,
        }
    if isinstance(message, SubmitTurnPayload):
        return MessageKind.SUBMIT_TURN, {
            "turn": encode_turn(message.turn),
            "client_revision": message.client_revision,
            "board_id": message.board_id,
        }
    if isinstance(message, TurnRejectedPayload):
        return MessageKind.TURN_REJECTED, {
            "reason": message.reason,
            "expected_revision": message.expected_revision,
        }
    if isinstance(message, StateEnvelope):
        return MessageKind.STATE_SYNC, _encode_envelope(message)
    if isinstance(message, MatchEnvelope):
        return MessageKind.MATCH_SYNC, _encode_match_envelope(message)
    if isinstance(message, LobbyState):
        return MessageKind.LOBBY_STATE, _encode_lobby(message)
    if isinstance(message, UndoRequest):
        return MessageKind.UNDO_REQUEST, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "session_id": message.session_id,
            "base_revision": message.base_revision,
            "plies": message.plies,
            "board_id": message.board_id,
        }
    if isinstance(message, UndoPending):
        return MessageKind.UNDO_PENDING, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "requester_side": message.requester_side.name,
            "plies": message.plies,
            "board_id": message.board_id,
            "requester_seat": message.requester_seat,
        }
    if isinstance(message, UndoDecision):
        return MessageKind.UNDO_DECISION, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "session_id": message.session_id,
            "accept": message.accept,
        }
    if isinstance(message, UndoResolved):
        return MessageKind.UNDO_RESOLVED, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "revision": message.revision,
            "accepted": message.accepted,
            "state": None if message.state is None else encode_state(message.state),
            "board_id": message.board_id,
        }
    raise ProtocolError(f"unsupported message: {type(message).__name__}")


def message_from_payload(
    kind: MessageKind, payload: dict[str, Any], *, mode=None
) -> object:
    try:
        return _decode_payload(kind, payload, mode=mode)
    except (KeyError, TypeError, ValueError, NetworkCodecError) as exc:
        raise ProtocolError("invalid payload") from exc


def _decode_payload(kind: MessageKind, payload: dict[str, Any], *, mode=None) -> object:
    if kind is MessageKind.HELLO:
        return HelloPayload(protocol=int(payload["protocol"]), package=str(payload["package"]))
    if kind is MessageKind.HELLO_OK:
        raw_side = payload.get("side")
        return HelloOkPayload(
            session_id=str(payload["session_id"]),
            seat=str(payload.get("seat") or "spectator"),
            mode_id=str(payload["mode_id"]),
            game_id=str(payload["game_id"]),
            protocol=int(payload["protocol"]),
            package=str(payload["package"]),
            is_host=bool(payload.get("is_host", False)),
            match_kind=str(payload.get("match_kind") or "single"),
            side=None if raw_side in (None, "") else PieceSide[str(raw_side)],
        )
    if kind is MessageKind.HELLO_REJECTED:
        return HelloRejectedPayload(reason=str(payload["reason"]))
    if kind is MessageKind.CLAIM_SEAT:
        return ClaimSeatPayload(seat=str(payload["seat"]))
    if kind is MessageKind.LEAVE_SEAT:
        return LeaveSeatPayload()
    if kind is MessageKind.START_MATCH:
        return StartMatchPayload()
    if kind is MessageKind.BRAIN_SELECT:
        return BrainSelectPayload(
            piece_type=str(payload["piece_type"]),
            board_id=payload.get("board_id"),
        )
    if kind is MessageKind.SUBMIT_TURN:
        return SubmitTurnPayload(
            turn=decode_turn(payload["turn"]),
            client_revision=int(payload["client_revision"]),
            board_id=payload.get("board_id"),
        )
    if kind is MessageKind.TURN_REJECTED:
        return TurnRejectedPayload(
            reason=str(payload["reason"]),
            expected_revision=int(payload["expected_revision"]),
        )
    if kind is MessageKind.STATE_SYNC:
        if mode is None:
            raise ProtocolError("mode is required to decode state")
        return _decode_envelope(payload, mode)
    if kind is MessageKind.MATCH_SYNC:
        if mode is None:
            raise ProtocolError("mode is required to decode match state")
        return _decode_match_envelope(payload, mode)
    if kind is MessageKind.LOBBY_STATE:
        return _decode_lobby(payload)
    if kind is MessageKind.UNDO_REQUEST:
        return UndoRequest(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            session_id=str(payload["session_id"]),
            base_revision=int(payload["base_revision"]),
            plies=int(payload.get("plies", 1)),
            board_id=payload.get("board_id"),
        )
    if kind is MessageKind.UNDO_PENDING:
        return UndoPending(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            requester_side=PieceSide[str(payload["requester_side"])],
            plies=int(payload["plies"]),
            board_id=payload.get("board_id"),
            requester_seat=payload.get("requester_seat"),
        )
    if kind is MessageKind.UNDO_DECISION:
        return UndoDecision(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            session_id=str(payload["session_id"]),
            accept=bool(payload["accept"]),
        )
    if kind is MessageKind.UNDO_RESOLVED:
        raw_state = payload.get("state")
        return UndoResolved(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            revision=int(payload["revision"]),
            accepted=bool(payload["accepted"]),
            state=None if raw_state is None else decode_state(raw_state, mode),
            board_id=payload.get("board_id"),
        )
    raise ProtocolError(f"unsupported kind: {kind.name}")


def _encode_envelope(envelope: StateEnvelope) -> dict[str, Any]:
    return {
        "game_id": envelope.game_id,
        "revision": envelope.revision,
        "state": encode_state(envelope.state),
        "clock": None if envelope.clock is None else _encode_clock(envelope.clock),
    }


def _decode_envelope(payload: dict[str, Any], mode) -> StateEnvelope:
    raw_clock = payload.get("clock")
    return StateEnvelope(
        game_id=str(payload["game_id"]),
        revision=int(payload["revision"]),
        state=decode_state(payload["state"], mode),
        clock=None if raw_clock is None else _decode_clock(raw_clock),
    )


def _encode_match_envelope(envelope: MatchEnvelope) -> dict[str, Any]:
    return {
        "game_id": envelope.game_id,
        "revision": envelope.revision,
        "match_kind": envelope.match_kind.name,
        "phase": envelope.phase.name,
        "boards": {board_id: encode_state(state) for board_id, state in envelope.boards.items()},
        "clocks": {board_id: _encode_clock(clock) for board_id, clock in envelope.clocks.items()},
        "chosen_piece_type": envelope.chosen_piece_type,
        "result": None
        if envelope.result is None
        else {
            "winner_team": envelope.result.winner_team,
            "reason": envelope.result.reason,
            "board_id": envelope.result.board_id,
        },
        "lobby": None if envelope.lobby is None else _encode_lobby(envelope.lobby),
    }


def _decode_match_envelope(payload: dict[str, Any], mode) -> MatchEnvelope:
    raw_result = payload.get("result")
    raw_lobby = payload.get("lobby")
    return MatchEnvelope(
        game_id=str(payload["game_id"]),
        revision=int(payload["revision"]),
        match_kind=MatchKind[str(payload["match_kind"])],
        phase=MatchPhase[str(payload["phase"])],
        boards={
            str(board_id): decode_state(state, mode)
            for board_id, state in (payload.get("boards") or {}).items()
        },
        clocks={
            str(board_id): _decode_clock(clock)
            for board_id, clock in (payload.get("clocks") or {}).items()
        },
        chosen_piece_type=payload.get("chosen_piece_type"),
        result=None
        if raw_result is None
        else MatchResult(
            winner_team=raw_result.get("winner_team"),
            reason=str(raw_result.get("reason") or ""),
            board_id=raw_result.get("board_id"),
        ),
        lobby=None if raw_lobby is None else _decode_lobby(raw_lobby),
    )


def _encode_lobby(lobby: LobbyState) -> dict[str, Any]:
    return {
        "game_id": lobby.game_id,
        "phase": lobby.phase.name,
        "host_session_id": lobby.host_session_id,
        "required_seats": list(lobby.required_seats),
        "occupants": [
            {
                "session_id": occupant.session_id,
                "seat": occupant.seat,
                "is_host": occupant.is_host,
            }
            for occupant in lobby.occupants
        ],
    }


def _decode_lobby(payload: dict[str, Any]) -> LobbyState:
    occupants = tuple(
        LobbyOccupant(
            session_id=str(item["session_id"]),
            seat=str(item["seat"]),
            is_host=bool(item.get("is_host", False)),
        )
        for item in payload.get("occupants") or ()
    )
    return LobbyState(
        game_id=str(payload["game_id"]),
        phase=MatchPhase[str(payload["phase"])],
        occupants=occupants,
        host_session_id=str(payload.get("host_session_id") or ""),
        required_seats=tuple(str(seat) for seat in payload.get("required_seats") or ()),
    )


def _encode_clock(snapshot: ClockSnapshot) -> dict[str, Any]:
    config = snapshot.time_control
    return {
        "revision": snapshot.revision,
        "running_side": None if snapshot.running_side is None else snapshot.running_side.name,
        "white_remaining_ms": snapshot.white_remaining_ms,
        "black_remaining_ms": snapshot.black_remaining_ms,
        "white_byoyomi_left": snapshot.white_byoyomi_left,
        "black_byoyomi_left": snapshot.black_byoyomi_left,
        "server_mono_ms": snapshot.server_mono_ms,
        "next_deadline_ms": snapshot.next_deadline_ms,
        "time_control": {
            "kind": config.kind.name,
            "initial_ms": list(config.initial_ms),
            "increment_ms": config.increment_ms,
            "delay_ms": config.delay_ms,
            "byoyomi_period_ms": config.byoyomi_period_ms,
            "byoyomi_periods": config.byoyomi_periods,
        },
    }


def _decode_clock(payload: dict[str, Any]) -> ClockSnapshot:
    raw_side = payload.get("running_side")
    raw_config = payload["time_control"]
    return ClockSnapshot(
        revision=int(payload["revision"]),
        running_side=None if raw_side in (None, "") else PieceSide[str(raw_side)],
        white_remaining_ms=int(payload["white_remaining_ms"]),
        black_remaining_ms=int(payload["black_remaining_ms"]),
        white_byoyomi_left=int(payload["white_byoyomi_left"]),
        black_byoyomi_left=int(payload["black_byoyomi_left"]),
        server_mono_ms=int(payload["server_mono_ms"]),
        next_deadline_ms=payload.get("next_deadline_ms"),
        time_control=TimeControlConfig(
            kind=TimeControlKind[str(raw_config["kind"])],
            initial_ms=(int(raw_config["initial_ms"][0]), int(raw_config["initial_ms"][1])),
            increment_ms=int(raw_config.get("increment_ms") or 0),
            delay_ms=int(raw_config.get("delay_ms") or 0),
            byoyomi_period_ms=int(raw_config.get("byoyomi_period_ms") or 0),
            byoyomi_periods=int(raw_config.get("byoyomi_periods") or 0),
        ),
    )


def local_hello() -> HelloPayload:
    return HelloPayload(protocol=PROTOCOL_VERSION, package=__version__)
