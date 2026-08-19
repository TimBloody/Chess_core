"""JSON-line framing for the LAN game protocol."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from chess_core import __version__
from chess_core.app.clock import ClockSnapshot
from chess_core.core.piece import PieceSide
from chess_core.infra.network_codec import (
    NetworkCodecError,
    decode_clock,
    decode_state,
    decode_turn,
    encode_clock,
    encode_state,
    encode_turn,
)
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    PROTOCOL_VERSION,
    HelloOkPayload,
    HelloPayload,
    HelloRejectedPayload,
    MessageKind,
    OpponentLeft,
    StateEnvelope,
    SubmitTurnPayload,
    TurnRejectedPayload,
    UndoDecision,
    UndoPending,
    UndoRequest,
    UndoResolved,
)

MAX_MESSAGE_BYTES = 1_048_576

__all__ = [
    "DEFAULT_GAME_PORT",
    "MAX_MESSAGE_BYTES",
    "PROTOCOL_VERSION",
    "ProtocolError",
    "decode_frame",
    "encode_frame",
    "local_hello",
    "message_from_payload",
    "message_to_payload",
]


class ProtocolError(ValueError):
    """Invalid or oversized protocol frame."""


def encode_frame(kind: MessageKind, payload: dict[str, Any]) -> bytes:
    text = json.dumps({"kind": kind.name, "payload": payload}, separators=(",", ":"))
    data = text.encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    return data + b"\n"


async def read_frame(reader: asyncio.StreamReader) -> tuple[MessageKind, dict[str, Any]]:
    line = await reader.readline()
    if not line:
        raise ConnectionError("connection closed")
    if len(line) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    return decode_frame(line)


def decode_frame(raw: bytes) -> tuple[MessageKind, dict[str, Any]]:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("message too large")
    line = raw.strip()
    if not line:
        raise ProtocolError("empty message")
    try:
        parsed = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("invalid json") from exc
    if not isinstance(parsed, dict) or "kind" not in parsed:
        raise ProtocolError("frame must be an object with kind")
    try:
        kind = MessageKind[str(parsed["kind"])]
    except KeyError as exc:
        raise ProtocolError(f"unknown message kind: {parsed.get('kind')!r}") from exc
    payload = parsed.get("payload") or {}
    if not isinstance(payload, dict):
        raise ProtocolError("payload must be an object")
    return kind, payload


def message_to_payload(message: object) -> tuple[MessageKind, dict[str, Any]]:
    if isinstance(message, StateEnvelope):
        return MessageKind.STATE_SYNC, _encode_envelope(message)
    if isinstance(message, SubmitTurnPayload):
        return MessageKind.SUBMIT_TURN, {
            "turn": encode_turn(message.turn),
            "client_revision": message.client_revision,
        }
    if isinstance(message, TurnRejectedPayload):
        return MessageKind.TURN_REJECTED, {
            "reason": message.reason,
            "expected_revision": message.expected_revision,
        }
    if isinstance(message, HelloPayload):
        return MessageKind.HELLO, {
            "protocol": message.protocol,
            "package": message.package,
        }
    if isinstance(message, HelloOkPayload):
        return MessageKind.HELLO_OK, {
            "session_id": message.session_id,
            "side": message.side.name,
            "mode_id": message.mode_id,
            "game_id": message.game_id,
            "protocol": message.protocol,
            "package": message.package,
        }
    if isinstance(message, HelloRejectedPayload):
        return MessageKind.HELLO_REJECTED, {"reason": message.reason}
    if isinstance(message, UndoRequest):
        return MessageKind.UNDO_REQUEST, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "session_id": message.session_id,
            "base_revision": message.base_revision,
            "plies": message.plies,
        }
    if isinstance(message, UndoPending):
        return MessageKind.UNDO_PENDING, {
            "game_id": message.game_id,
            "request_id": message.request_id,
            "requester_side": message.requester_side.name,
            "plies": message.plies,
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
        }
    if isinstance(message, OpponentLeft):
        return MessageKind.OPPONENT_LEFT, {
            "game_id": message.game_id,
            "session_id": message.session_id,
        }
    if isinstance(message, ClockSnapshot):
        return MessageKind.CLOCK_SYNC, encode_clock(message)
    raise ProtocolError(f"cannot encode message: {type(message).__name__}")


def message_from_payload(kind: MessageKind, payload: dict[str, Any]) -> object:
    try:
        return _decode_payload(kind, payload)
    except (KeyError, TypeError, ValueError, NetworkCodecError) as exc:
        raise ProtocolError(f"invalid {kind.name} payload") from exc


def _decode_payload(kind: MessageKind, payload: dict[str, Any]) -> object:
    if kind is MessageKind.HELLO:
        return HelloPayload(protocol=int(payload["protocol"]), package=str(payload["package"]))
    if kind is MessageKind.HELLO_OK:
        return HelloOkPayload(
            session_id=str(payload["session_id"]),
            side=PieceSide[str(payload["side"])],
            mode_id=str(payload["mode_id"]),
            game_id=str(payload["game_id"]),
            protocol=int(payload["protocol"]),
            package=str(payload["package"]),
        )
    if kind is MessageKind.HELLO_REJECTED:
        return HelloRejectedPayload(reason=str(payload["reason"]))
    if kind is MessageKind.STATE_SYNC:
        return _decode_envelope(payload)
    if kind is MessageKind.SUBMIT_TURN:
        return SubmitTurnPayload(
            turn=decode_turn(payload["turn"]),
            client_revision=int(payload["client_revision"]),
        )
    if kind is MessageKind.TURN_REJECTED:
        return TurnRejectedPayload(
            reason=str(payload["reason"]),
            expected_revision=int(payload["expected_revision"]),
        )
    if kind is MessageKind.UNDO_REQUEST:
        return UndoRequest(
            game_id=str(payload.get("game_id") or ""),
            request_id=str(payload.get("request_id") or ""),
            session_id=str(payload.get("session_id") or ""),
            base_revision=int(payload.get("base_revision") or 0),
            plies=int(payload.get("plies") or 1),
        )
    if kind is MessageKind.UNDO_PENDING:
        return UndoPending(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            requester_side=PieceSide[str(payload["requester_side"])],
            plies=int(payload["plies"]),
        )
    if kind is MessageKind.UNDO_DECISION:
        return UndoDecision(
            game_id=str(payload.get("game_id") or ""),
            request_id=str(payload["request_id"]),
            session_id=str(payload.get("session_id") or ""),
            accept=bool(payload["accept"]),
        )
    if kind is MessageKind.UNDO_RESOLVED:
        raw_state = payload.get("state")
        return UndoResolved(
            game_id=str(payload["game_id"]),
            request_id=str(payload["request_id"]),
            revision=int(payload["revision"]),
            accepted=bool(payload["accepted"]),
            state=None if raw_state is None else decode_state(raw_state),
        )
    if kind is MessageKind.CLOCK_SYNC:
        return decode_clock(payload)
    if kind is MessageKind.OPPONENT_LEFT:
        return OpponentLeft(
            game_id=str(payload["game_id"]),
            session_id=str(payload["session_id"]),
        )
    raise ProtocolError(f"unsupported kind: {kind.name}")


def _encode_envelope(envelope: StateEnvelope) -> dict[str, Any]:
    return {
        "game_id": envelope.game_id,
        "revision": envelope.revision,
        "state": encode_state(envelope.state),
        "clock": None if envelope.clock is None else encode_clock(envelope.clock),
        "last_turn": None if envelope.last_turn is None else encode_turn(envelope.last_turn),
    }


def _decode_envelope(payload: dict[str, Any]) -> StateEnvelope:
    raw_clock = payload.get("clock")
    raw_turn = payload.get("last_turn")
    return StateEnvelope(
        game_id=str(payload["game_id"]),
        revision=int(payload["revision"]),
        state=decode_state(payload["state"]),
        clock=None if raw_clock is None else decode_clock(raw_clock),
        last_turn=None if raw_turn is None else decode_turn(raw_turn),
    )


def local_hello() -> HelloPayload:
    return HelloPayload(protocol=PROTOCOL_VERSION, package=__version__)
