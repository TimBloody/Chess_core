"""JSON snapshot conversion for tournament state. No filesystem I/O."""

from __future__ import annotations

from chess_core.app.tournament.models import (
    AuditEntry,
    Pairing,
    PairingSystem,
    Player,
    PlayerStatus,
    ResultKind,
)
from chess_core.app.tournament.state import TournamentSettings, TournamentState

SNAPSHOT_VERSION = 1


def state_to_dict(state: TournamentState) -> dict:
    return {
        "version": SNAPSHOT_VERSION,
        "settings": {
            "name": state.settings.name,
            "system": state.settings.system.value,
            "declared_rounds": state.settings.declared_rounds,
            "rr_cycles": state.settings.rr_cycles,
            "initial_color": state.settings.initial_color,
            "pairing_engine": state.settings.pairing_engine,
            "seed": state.settings.seed,
            "list_closed": state.settings.list_closed,
            "site": state.settings.site,
            "arbiter": state.settings.arbiter,
            "time_control": state.settings.time_control,
        },
        "current_round": state.current_round,
        "players": [_player_to_dict(player) for player in state.players],
        "pairings": [_pairing_to_dict(pairing) for pairing in state.pairings],
        "audit": [_audit_to_dict(entry) for entry in state.audit],
        "scheduled_byes": [list(item) for item in state.scheduled_byes],
    }


def state_from_dict(payload: dict) -> TournamentState:
    version = int(payload.get("version", SNAPSHOT_VERSION))
    if version > SNAPSHOT_VERSION:
        raise ValueError(f"unsupported tournament snapshot version: {version}")
    raw_settings = payload.get("settings") or {}
    settings = TournamentSettings(
        name=str(raw_settings.get("name") or "Tournament"),
        system=PairingSystem(raw_settings.get("system") or PairingSystem.SWISS.value),
        declared_rounds=int(raw_settings.get("declared_rounds") or 5),
        rr_cycles=int(raw_settings.get("rr_cycles") or 1),
        initial_color=str(raw_settings.get("initial_color") or "white"),
        pairing_engine=str(raw_settings.get("pairing_engine") or "native_dutch_2026"),
        seed=int(raw_settings.get("seed") or 1),
        list_closed=bool(raw_settings.get("list_closed", False)),
        site=str(raw_settings.get("site") or ""),
        arbiter=str(raw_settings.get("arbiter") or ""),
        time_control=str(raw_settings.get("time_control") or ""),
    )
    players = tuple(_player_from_dict(item) for item in payload.get("players") or ())
    pairings = tuple(_pairing_from_dict(item) for item in payload.get("pairings") or ())
    audit = tuple(_audit_from_dict(item) for item in payload.get("audit") or ())
    scheduled_raw = payload.get("scheduled_byes") or ()
    scheduled_byes = tuple(
        (str(item[0]), str(item[1]))
        for item in scheduled_raw
        if isinstance(item, (list, tuple)) and len(item) >= 2
    )
    return TournamentState(
        settings=settings,
        players=players,
        pairings=pairings,
        current_round=int(payload.get("current_round") or 0),
        audit=audit,
        scheduled_byes=scheduled_byes,
        version=version,
    )


def _player_to_dict(player: Player) -> dict:
    return {
        "player_id": player.player_id,
        "name": player.name,
        "rating": player.rating,
        "team": player.team,
        "title": player.title,
        "federation": player.federation,
        "status": player.status.value,
        "start_number": player.start_number,
    }


def _player_from_dict(payload: dict) -> Player:
    return Player(
        player_id=str(payload["player_id"]),
        name=str(payload["name"]),
        rating=int(payload.get("rating") or 0),
        team=payload.get("team"),
        title=str(payload.get("title") or ""),
        federation=str(payload.get("federation") or ""),
        status=PlayerStatus(payload.get("status") or PlayerStatus.ACTIVE.value),
        start_number=int(payload.get("start_number") or 0),
    )


def _pairing_to_dict(pairing: Pairing) -> dict:
    return {
        "round_index": pairing.round_index,
        "board": pairing.board,
        "white_id": pairing.white_id,
        "black_id": pairing.black_id,
        "result": pairing.result,
        "result_kind": pairing.result_kind.value if pairing.result_kind is not None else None,
        "manual": pairing.manual,
    }


def _pairing_from_dict(payload: dict) -> Pairing:
    kind_raw = payload.get("result_kind")
    return Pairing(
        round_index=int(payload["round_index"]),
        board=int(payload["board"]),
        white_id=payload.get("white_id"),
        black_id=payload.get("black_id"),
        result=payload.get("result"),
        result_kind=ResultKind(kind_raw) if kind_raw else None,
        manual=bool(payload.get("manual", False)),
    )


def _audit_to_dict(entry: AuditEntry) -> dict:
    return {
        "action": entry.action,
        "reason": entry.reason,
        "round_index": entry.round_index,
        "detail": entry.detail,
        "warnings": list(entry.warnings),
    }


def _audit_from_dict(payload: dict) -> AuditEntry:
    warnings = payload.get("warnings") or ()
    return AuditEntry(
        action=str(payload.get("action") or ""),
        reason=str(payload.get("reason") or ""),
        round_index=payload.get("round_index"),
        detail=str(payload.get("detail") or ""),
        warnings=tuple(str(item) for item in warnings),
    )
