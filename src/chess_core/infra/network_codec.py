"""JSON codec for network GameState / Turn payloads."""

from __future__ import annotations

from typing import Any

from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import (
    DropAction,
    MoveAction,
    PassAction,
    PlaceBlockerAction,
    TransformAction,
    Turn,
)
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import BoardState, GameState, HandsState


class NetworkCodecError(ValueError):
    pass


def encode_state(state: GameState) -> dict[str, Any]:
    extras = {
        key: _encode_extra(value)
        for key, value in state.extras.items()
        if key != "mode"
    }
    payload: dict[str, Any] = {
        "files": state.board_state.board.shape.files,
        "ranks": state.board_state.board.shape.ranks,
        "side_to_move": state.side_to_move.name,
        "cells": {
            str(index): None if piece is None else _encode_piece(piece)
            for index, piece in state.board_state.cells.items()
        },
        "extras": extras,
    }
    if state.hands is not None:
        payload["hands"] = {
            side.name: [_encode_piece(piece) for piece in pieces]
            for side, pieces in state.hands.by_side.items()
        }
    else:
        payload["hands"] = None
    if state.repetition_log:
        payload["repetition_log"] = [_encode_key(key) for key in state.repetition_log]
    return payload


def decode_state(payload: dict[str, Any], mode: GameMode) -> GameState:
    files = int(payload["files"])
    ranks = int(payload["ranks"])
    board = Board(BoardShape(files=files, ranks=ranks))
    cells: dict[int, Piece | None] = {}
    raw_cells = payload.get("cells") or {}
    if not isinstance(raw_cells, dict):
        raise NetworkCodecError("cells must be an object")
    for key, value in raw_cells.items():
        cells[int(key)] = None if value is None else _decode_piece(value)
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
    extras = _decode_extras(payload.get("extras") or {})
    extras["mode"] = mode
    log = payload.get("repetition_log")
    repetition_log = tuple(_decode_key(item) for item in log) if isinstance(log, list) else ()
    return GameState(
        board_state=BoardState(board, cells),
        side_to_move=PieceSide[str(payload["side_to_move"])],
        hands=hands,
        extras=extras,
        repetition_log=repetition_log,
    )


def encode_turn(turn: Turn) -> dict[str, Any]:
    return {
        "side": turn.side.name,
        "actions": [_encode_action(action) for action in turn.actions],
    }


def decode_turn(payload: dict[str, Any]) -> Turn:
    return Turn(
        PieceSide[str(payload["side"])],
        [_decode_action(item) for item in payload.get("actions") or ()],
    )


def _encode_piece(piece: Piece) -> dict[str, Any]:
    return {
        "type": piece.piece_type.name,
        "side": piece.side.name,
        "state": piece.state,
    }


def _decode_piece(payload: object) -> Piece:
    if not isinstance(payload, dict):
        raise NetworkCodecError("piece must be an object")
    return Piece(
        PieceTypeId(str(payload["type"])),
        PieceSide[str(payload["side"])],
        payload.get("state"),
    )


def _encode_action(action: object) -> dict[str, Any]:
    if isinstance(action, MoveAction):
        payload = {
            "kind": "move",
            "from": _encode_square(action.from_square),
            "to": _encode_square(action.to_square),
        }
        if action.promotion_choice is not None:
            payload["promotion"] = action.promotion_choice.name
        if action.jumped:
            payload["jumped"] = [_encode_square(square) for square in action.jumped]
        return payload
    if isinstance(action, DropAction):
        return {
            "kind": "drop",
            "type": action.piece_type.name,
            "to": _encode_square(action.to_square),
            "face": action.face,
        }
    if isinstance(action, PlaceBlockerAction):
        return {"kind": "blocker", "square": _encode_square(action.square)}
    if isinstance(action, TransformAction):
        return {
            "kind": "transform",
            "square": _encode_square(action.square),
            "type": action.new_type.name,
        }
    if isinstance(action, PassAction):
        return {"kind": "pass"}
    raise NetworkCodecError(f"unsupported action: {type(action).__name__}")


def _decode_action(payload: object) -> object:
    if not isinstance(payload, dict):
        raise NetworkCodecError("action must be an object")
    kind = payload.get("kind")
    if kind == "move":
        promo = payload.get("promotion")
        jumped = tuple(_decode_square(item) for item in payload.get("jumped") or ())
        return MoveAction(
            _decode_square(payload["from"]),
            _decode_square(payload["to"]),
            None if promo is None else PieceTypeId(str(promo)),
            jumped,
        )
    if kind == "drop":
        return DropAction(
            PieceTypeId(str(payload["type"])),
            _decode_square(payload["to"]),
            payload.get("face"),
        )
    if kind == "blocker":
        return PlaceBlockerAction(_decode_square(payload["square"]))
    if kind == "transform":
        return TransformAction(
            _decode_square(payload["square"]),
            PieceTypeId(str(payload["type"])),
        )
    if kind == "pass":
        return PassAction()
    raise NetworkCodecError(f"unknown action kind: {kind}")


def _encode_square(square: Square) -> dict[str, int]:
    return {"file": square.file, "rank": square.rank}


def _decode_square(payload: object) -> Square:
    if not isinstance(payload, dict):
        raise NetworkCodecError("square must be an object")
    return Square(int(payload["file"]), int(payload["rank"]))


def _encode_key(value: object) -> object:
    if isinstance(value, tuple):
        return [_encode_key(item) for item in value]
    return value


def _decode_key(value: object) -> object:
    if isinstance(value, list):
        return tuple(_decode_key(item) for item in value)
    return value


def _encode_extra(value: object) -> object:
    if isinstance(value, Square):
        return {"__square__": _encode_square(value)}
    if isinstance(value, set):
        return {"__set__": sorted(str(item) for item in value)}
    if isinstance(value, Piece):
        return {"__piece__": _encode_piece(value)}
    if isinstance(value, list):
        return [_encode_extra(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode_extra(item) for key, item in value.items()}
    if isinstance(value, PieceSide):
        return {"__side__": value.name}
    return value


def _decode_extras(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise NetworkCodecError("extras must be an object")
    return {str(key): _decode_extra(value) for key, value in payload.items()}


def _decode_extra(value: object) -> object:
    if isinstance(value, dict):
        if "__square__" in value:
            return _decode_square(value["__square__"])
        if "__set__" in value:
            return set(value["__set__"])
        if "__piece__" in value:
            return _decode_piece(value["__piece__"])
        if "__side__" in value:
            return PieceSide[str(value["__side__"])]
        return {str(key): _decode_extra(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_extra(item) for item in value]
    return value
