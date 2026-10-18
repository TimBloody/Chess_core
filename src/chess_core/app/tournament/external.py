"""Boundary for an official external pairing engine (JaVaFo / bbpPairings / Swiss-Manager).

The adapter is a dummy until an executable is configured. Tests may inject a
callable that returns TRF text so native and external pairings can be compared.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from chess_core.app.tournament.engine import EngineNotConfiguredError
from chess_core.app.tournament.models import Pairing, Player
from chess_core.app.tournament.trf import pairings_from_trf26, tournament_to_trf26

TrfRunner = Callable[[str, int], str]


class ExternalOfficialEngineAdapter:
    engine_id = "external_official"

    def __init__(
        self,
        *,
        executable: str | Path | None = None,
        runner: TrfRunner | None = None,
    ) -> None:
        self.executable = Path(executable) if executable else _configured_executable()
        self.runner = runner

    def pair_round(
        self,
        players: tuple[Player, ...],
        history: tuple[Pairing, ...],
        *,
        round_index: int,
        declared_rounds: int,
        initial_color: str = "white",
    ) -> tuple[Pairing, ...]:
        del initial_color
        trf = tournament_to_trf26(
            name="Chess Core",
            players=players,
            pairings=history,
            declared_rounds=declared_rounds,
        )
        if self.runner is not None:
            output = self.runner(trf, round_index)
            return pairings_from_trf26(output, players, round_index=round_index)
        if self.executable is None or not self.executable.exists():
            raise EngineNotConfiguredError(
                "official pairing engine is not configured; native Dutch 2026 is used instead"
            )
        output = _run_executable(self.executable, trf, round_index)
        return pairings_from_trf26(output, players, round_index=round_index)


def compare_pairings(
    native: tuple[Pairing, ...],
    external: tuple[Pairing, ...],
) -> tuple[str, ...]:
    """Diagnostic report. Never silently replaces native pairings."""
    issues: list[str] = []
    native_pairs = [_pair_key(item) for item in native]
    external_pairs = [_pair_key(item) for item in external]
    if native_pairs != external_pairs:
        issues.append(
            "pairing mismatch: native="
            + ",".join(native_pairs)
            + " external="
            + ",".join(external_pairs)
        )
    return tuple(issues)


def _pair_key(pairing: Pairing) -> str:
    left = pairing.white_id or "BYE"
    right = pairing.black_id or "BYE"
    return f"{pairing.board}:{left}-{right}"


def _configured_executable() -> Path | None:
    env = os.environ.get("CHESS_CORE_PAIRING_ENGINE")
    if env:
        return Path(env)
    return None


def _run_executable(executable: Path, trf: str, round_index: int) -> str:
    completed = subprocess.run(
        [str(executable), "--round", str(round_index)],
        input=trf,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise EngineNotConfiguredError(completed.stderr.strip() or "official engine failed")
    return completed.stdout
