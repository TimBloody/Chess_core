"""Read/write tournament manager snapshots and FIDE/Swiss-Manager exchange files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from chess_core.app.tournament.serialization import state_from_dict, state_to_dict
from chess_core.app.tournament.state import TournamentState
from chess_core.app.tournament.trf import looks_like_trf, state_from_trf, tournament_to_trf26
from chess_core.app.tournament.tunx import is_tunx, state_from_tunx
from chess_core.infra.paths import project_root

SNAPSHOT_SUFFIX = ".tournament.json"
_TEAM_EXTENSIONS = {".tumx", ".tutx"}
_JSON_EXTENSIONS = {".json"}
_TRF_EXTENSIONS = {".trf", ".txt"}


def default_tournaments_dir() -> Path:
    env = os.environ.get("CHESS_CORE_TOURNAMENTS_DIR")
    if env:
        return Path(env)
    local = project_root() / "tournaments"
    if local.is_dir():
        return local
    return Path.home() / "chess-core-tournaments"


def save_tournament(state: TournamentState, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state_to_dict(state), ensure_ascii=False, indent=2)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(target)
    return target


def save_trf(state: TournamentState, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = tournament_to_trf26(
        name=state.settings.name,
        players=state.players,
        pairings=state.pairings,
        declared_rounds=max(state.settings.declared_rounds, state.current_round, 1),
        site=state.settings.site,
        arbiter=state.settings.arbiter,
        time_control=state.settings.time_control,
        system=state.settings.system,
    )
    target.write_bytes(text.encode("utf-8-sig"))
    return target


def load_tournament(path: str | Path) -> TournamentState:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix in _TEAM_EXTENSIONS:
        raise ValueError("командные турниры Swiss-Manager (.TUMx/.TUTx) пока не поддерживаются")
    data = target.read_bytes()
    if is_tunx(data):
        return state_from_tunx(data)
    text = _decode_text(data)
    stripped = text.lstrip("\ufeff").lstrip()
    if stripped.startswith("{") or suffix in _JSON_EXTENSIONS:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("tournament snapshot must be a JSON object")
        return state_from_dict(payload)
    if looks_like_trf(stripped) or suffix in _TRF_EXTENSIONS:
        return state_from_trf(text)
    raise ValueError(
        "неизвестный формат турнира. Откройте JSON, TRF16 (.trf) или Swiss-Manager .TUNX/.TURX. "
        "Запись в .TUN/.TUNX недоступна — в Swiss-Manager импортируйте TRF16."
    )


def _decode_text(data: bytes) -> str:
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16le")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16be")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251")
