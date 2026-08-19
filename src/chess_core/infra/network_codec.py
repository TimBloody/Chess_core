"""JSON-safe encoding of game state, turns, and extras for the LAN protocol."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from importlib import import_module
from typing import Any

from chess_core.app.clock import ClockSnapshot
from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import (
    DropAction,
    MoveAction,
    PassAction,
    PlaceAction,
    PlaceBlockerAction,
    TransformAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import GameModeRegistry, default_registry
from chess_core.core.state import BoardState, GameState, HandsState, HistoryState
from chess_core.core.time_control import TimeControlConfig, TimeControlKind

_TAG = "__t__"

_WIRE_MODE_IDS = {
    "classic_chess": "chess",
    "duck_chess": "duck",
    "cylindrical_chess": "cylindrical",
}


class NetworkCodecError(ValueError):
    """Raised when a value cannot be encoded or decoded for the wire format."""


def encode_state(state: GameState) -> dict[str, Any]:
    mode = state.extras.get("mode")
    if not isinstance(mode, GameMode):
        raise NetworkCodecError("GameState extras must include a GameMode under 'mode'")
    occupied: dict[str, Any] = {}
    for index, piece in state.board_state.iter_occupied():
        occupied[str(index)] = _encode_piece(piece)
    payload: dict[str, Any] = {
        "mode_id": resolvable_mode_id(mode),
        "files": state.board_state.board.shape.files,
        "ranks": state.board_state.board.shape.ranks,
        "side_to_move": state.side_to_move.name,
        "cells": occupied,
        "extras": encode_extras(state.extras),
        "history": {
            "actions": [encode_action(action) for action in state.history.actions],
            "metadata": [encode_value(item) for item in state.history.metadata],
        },
    }
    if state.hands is not None:
        payload["hands"] = {
            side.name: [_encode_piece(piece) for piece in pieces]
            for side, pieces in state.hands.by_side.items()
        }
    else:
        payload["hands"] = None
    return payload


def decode_state(
    payload: dict[str, Any],
    *,
    registry: GameModeRegistry | None = None,
) -> GameState:
    if not isinstance(payload, dict):
        raise NetworkCodecError("state payload must be an object")
    mode_id = payload.get("mode_id")
    if not isinstance(mode_id, str) or not mode_id:
        raise NetworkCodecError("state payload is missing mode_id")
    resolved = (registry or default_registry).get(mode_id)
    files = int(payload["files"])
    ranks = int(payload["ranks"])
    board = Board(BoardShape(files, ranks))
    cells: dict[int, Piece | None] = {index: None for index in range(board.shape.cell_count)}
    raw_cells = payload.get("cells") or {}
    if not isinstance(raw_cells, dict):
        raise NetworkCodecError("cells must be an object")
    for key, raw_piece in raw_cells.items():
        cells[int(key)] = _decode_piece(raw_piece)
    hands = None
    raw_hands = payload.get("hands")
    if raw_hands is not None:
        if not isinstance(raw_hands, dict):
            raise NetworkCodecError("hands must be an object or null")
        hands = HandsState(
            {
                PieceSide[side_name]: [_decode_piece(item) for item in pieces]
                for side_name, pieces in raw_hands.items()
            }
        )
    raw_history = payload.get("history") or {}
    history = HistoryState(
        actions=[decode_action(item) for item in raw_history.get("actions") or ()],
        metadata=[decode_value(item) for item in raw_history.get("metadata") or ()],
    )
    extras = decode_extras(payload.get("extras") or {})
    extras["mode"] = resolved
    return GameState(
        board_state=BoardState(board, cells),
        side_to_move=PieceSide[str(payload["side_to_move"])],
        hands=hands,
        history=history,
        extras=extras,
    )


def encode_extras(extras: dict[str, Any]) -> dict[str, Any]:
    encoded: dict[str, Any] = {}
    for key, value in extras.items():
        if key == "mode":
            continue
        encoded[key] = encode_value(value)
    return encoded


def decode_extras(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NetworkCodecError("extras must be an object")
    return {key: decode_value(value) for key, value in payload.items() if key != "mode"}


def resolvable_mode_id(
    mode: GameMode, registry: GameModeRegistry | None = None
) -> str:
    """Return a registry key the peer can pass to ``registry.get``."""
    aliased = _WIRE_MODE_IDS.get(mode.id, mode.id)
    resolved = registry or default_registry
    if _registry_contains(resolved, aliased):
        return aliased
    if _registry_contains(resolved, mode.id):
        return mode.id
    return aliased


def _registry_contains(registry: GameModeRegistry, mode_id: str) -> bool:
    try:
        registry.get(mode_id)
    except KeyError:
        return False
    return True


def encode_turn(turn: Turn) -> dict[str, Any]:
    return {
        "side": turn.side.name,
        "actions": [encode_action(action) for action in turn.actions],
    }


def decode_turn(payload: dict[str, Any]) -> Turn:
    if not isinstance(payload, dict):
        raise NetworkCodecError("turn payload must be an object")
    return Turn(
        PieceSide[str(payload["side"])],
        [decode_action(item) for item in payload.get("actions") or ()],
    )


def encode_action(action: object) -> dict[str, Any]:
    if isinstance(action, MoveAction):
        return {
            "kind": "MOVE_PIECE",
            "from": _encode_square(action.from_square),
            "to": _encode_square(action.to_square),
            "promotion": action.promotion_choice.name if action.promotion_choice else None,
            "path": [_encode_square(square) for square in action.path],
            "captured": [_encode_square(square) for square in action.captured_squares],
        }
    if isinstance(action, DropAction):
        return {
            "kind": "DROP_PIECE",
            "piece_type": action.piece_type.name,
            "to": _encode_square(action.to_square),
            "face": action.face,
        }
    if isinstance(action, PlaceAction):
        return {
            "kind": "PLACE_PIECE",
            "piece_type": action.piece_type.name,
            "to": _encode_square(action.to_square),
            "face": action.face,
        }
    if isinstance(action, TransformAction):
        return {
            "kind": "TRANSFORM_PIECE",
            "square": _encode_square(action.square),
            "new_type": action.new_type.name,
        }
    if isinstance(action, PlaceBlockerAction):
        return {"kind": "PLACE_BLOCKER", "square": _encode_square(action.square)}
    if isinstance(action, PassAction):
        return {"kind": "PASS"}
    raise NetworkCodecError(f"unsupported action: {type(action).__name__}")


def decode_action(payload: dict[str, Any]) -> object:
    if not isinstance(payload, dict):
        raise NetworkCodecError("action payload must be an object")
    kind = payload.get("kind")
    if kind == "MOVE_PIECE":
        promotion = payload.get("promotion")
        return MoveAction(
            _decode_square(payload["from"]),
            _decode_square(payload["to"]),
            PieceTypeId(promotion) if promotion else None,
            tuple(_decode_square(item) for item in payload.get("path") or ()),
            tuple(_decode_square(item) for item in payload.get("captured") or ()),
        )
    if kind == "DROP_PIECE":
        return DropAction(
            PieceTypeId(str(payload["piece_type"])),
            _decode_square(payload["to"]),
            payload.get("face"),
        )
    if kind == "PLACE_PIECE":
        return PlaceAction(
            PieceTypeId(str(payload["piece_type"])),
            _decode_square(payload["to"]),
            payload.get("face"),
        )
    if kind == "TRANSFORM_PIECE":
        return TransformAction(
            _decode_square(payload["square"]),
            PieceTypeId(str(payload["new_type"])),
        )
    if kind == "PLACE_BLOCKER":
        return PlaceBlockerAction(_decode_square(payload["square"]))
    if kind == "PASS":
        return PassAction()
    raise NetworkCodecError(f"unsupported action kind: {kind!r}")


def encode_clock(snapshot: ClockSnapshot) -> dict[str, Any]:
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
            "kind": snapshot.time_control.kind.name,
            "initial_ms": list(snapshot.time_control.initial_ms),
            "increment_ms": snapshot.time_control.increment_ms,
            "delay_ms": snapshot.time_control.delay_ms,
            "byoyomi_period_ms": snapshot.time_control.byoyomi_period_ms,
            "byoyomi_periods": snapshot.time_control.byoyomi_periods,
        },
    }


def decode_clock(payload: dict[str, Any]) -> ClockSnapshot:
    raw_control = payload["time_control"]
    running = payload.get("running_side")
    return ClockSnapshot(
        revision=int(payload["revision"]),
        running_side=None if running is None else PieceSide[str(running)],
        white_remaining_ms=int(payload["white_remaining_ms"]),
        black_remaining_ms=int(payload["black_remaining_ms"]),
        white_byoyomi_left=int(payload["white_byoyomi_left"]),
        black_byoyomi_left=int(payload["black_byoyomi_left"]),
        server_mono_ms=int(payload["server_mono_ms"]),
        next_deadline_ms=(
            None if payload.get("next_deadline_ms") is None else int(payload["next_deadline_ms"])
        ),
        time_control=TimeControlConfig(
            kind=TimeControlKind[str(raw_control["kind"])],
            initial_ms=(int(raw_control["initial_ms"][0]), int(raw_control["initial_ms"][1])),
            increment_ms=int(raw_control.get("increment_ms") or 0),
            delay_ms=int(raw_control.get("delay_ms") or 0),
            byoyomi_period_ms=int(raw_control.get("byoyomi_period_ms") or 0),
            byoyomi_periods=int(raw_control.get("byoyomi_periods") or 0),
        ),
    )


def encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, GameMode):
        raise NetworkCodecError("cannot encode GameMode; send mode_id instead")
    if isinstance(value, Square):
        return {_TAG: "square", "file": value.file, "rank": value.rank}
    if isinstance(value, PieceSide):
        return {_TAG: "side", "name": value.name}
    if isinstance(value, PieceTypeId):
        return {_TAG: "piece_type", "name": value.name}
    if isinstance(value, Piece):
        return {_TAG: "piece", "value": _encode_piece(value)}
    if isinstance(value, Enum):
        return {
            _TAG: "enum",
            "cls": _qualname(type(value)),
            "name": value.name,
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _TAG: "dataclass",
            "cls": _qualname(type(value)),
            "fields": {
                item.name: encode_value(getattr(value, item.name))
                for item in fields(value)
            },
        }
    if isinstance(value, dict):
        return {
            _TAG: "dict",
            "items": [[encode_value(key), encode_value(item)] for key, item in value.items()],
        }
    if isinstance(value, tuple):
        return {_TAG: "tuple", "items": [encode_value(item) for item in value]}
    if isinstance(value, list):
        return {_TAG: "list", "items": [encode_value(item) for item in value]}
    if isinstance(value, set):
        return {_TAG: "set", "frozen": False, "items": [encode_value(item) for item in value]}
    if isinstance(value, frozenset):
        return {_TAG: "set", "frozen": True, "items": [encode_value(item) for item in value]}
    raise NetworkCodecError(f"cannot encode {type(value).__name__} for network extras")


def decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or _TAG not in value:
        return value
    tag = value[_TAG]
    if tag == "square":
        return Square(int(value["file"]), int(value["rank"]))
    if tag == "side":
        return PieceSide[str(value["name"])]
    if tag == "piece_type":
        return PieceTypeId(str(value["name"]))
    if tag == "piece":
        return _decode_piece(value["value"])
    if tag == "enum":
        cls = _load_chess_core_type(str(value["cls"]))
        return cls[str(value["name"])]
    if tag == "dataclass":
        cls = _load_chess_core_type(str(value["cls"]))
        raw_fields = value.get("fields") or {}
        return cls(**{name: decode_value(item) for name, item in raw_fields.items()})
    if tag == "dict":
        return {decode_value(key): decode_value(item) for key, item in value.get("items") or ()}
    if tag == "tuple":
        return tuple(decode_value(item) for item in value.get("items") or ())
    if tag == "list":
        return [decode_value(item) for item in value.get("items") or ()]
    if tag == "set":
        items = [decode_value(item) for item in value.get("items") or ()]
        return frozenset(items) if value.get("frozen") else set(items)
    raise NetworkCodecError(f"unknown extras tag: {tag!r}")


def _encode_piece(piece: Piece) -> dict[str, Any]:
    return {
        "type": piece.piece_type.name,
        "side": piece.side.name,
        "state": None if piece.state is None else encode_value(piece.state),
    }


def _decode_piece(payload: dict[str, Any] | None) -> Piece:
    if not isinstance(payload, dict):
        raise NetworkCodecError("piece payload must be an object")
    raw_state = payload.get("state")
    return Piece(
        PieceTypeId(str(payload["type"])),
        PieceSide[str(payload["side"])],
        None if raw_state is None else decode_value(raw_state),
    )


def _encode_square(square: Square) -> dict[str, int]:
    return {"file": square.file, "rank": square.rank}


def _decode_square(payload: dict[str, Any]) -> Square:
    return Square(int(payload["file"]), int(payload["rank"]))


def _qualname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _load_chess_core_type(path: str) -> type:
    if not path.startswith("chess_core."):
        raise NetworkCodecError(f"refusing to import {path!r}")
    module_name, _, attr = path.rpartition(".")
    if "." in attr:
        raise NetworkCodecError(f"unsupported type path: {path!r}")
    module = import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise NetworkCodecError(f"unknown type: {path}") from exc
