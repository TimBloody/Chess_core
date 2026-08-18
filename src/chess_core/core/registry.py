"""Register and resolve GameMode by id (no UI/infra imports)."""

from __future__ import annotations

from typing import Callable

from chess_core.core.gamemode import GameMode

ModeFactory = Callable[[], GameMode]


class GameModeRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ModeFactory] = {}

    def register(self, mode_id: str, factory: ModeFactory) -> None:
        if not mode_id:
            raise ValueError("mode_id must not be empty")
        self._factories[mode_id] = factory

    def get(self, mode_id: str) -> GameMode:
        try:
            factory = self._factories[mode_id]
        except KeyError as exc:
            raise KeyError(f"unknown game mode: {mode_id}") from exc
        return factory()

    def list_modes(self) -> list[str]:
        return sorted(self._factories)


default_registry = GameModeRegistry()
