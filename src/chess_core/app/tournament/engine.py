"""Pairing engine contract shared by native Dutch 2026 and external adapters."""

from __future__ import annotations

from typing import Protocol

from chess_core.app.tournament.models import Pairing, Player


class PairingEngine(Protocol):
    engine_id: str

    def pair_round(
        self,
        players: tuple[Player, ...],
        history: tuple[Pairing, ...],
        *,
        round_index: int,
        declared_rounds: int,
        initial_color: str = "white",
    ) -> tuple[Pairing, ...]:
        ...


class EngineNotConfiguredError(RuntimeError):
    """Raised when an external official pairing engine is not available."""
