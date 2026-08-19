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
        if mode_id in self._factories:
            return self._factories[mode_id]()
        if "+" in mode_id:
            from chess_core.modes.variant_composition import (
                compose_chess_mode,
                parse_modifier_ids_from_mode_id,
            )

            modifier_ids = parse_modifier_ids_from_mode_id(mode_id)
            if modifier_ids or mode_id == "chess":
                return compose_chess_mode(
                    modifier_ids,
                    mode_id=mode_id,
                )
        raise KeyError(f"unknown game mode: {mode_id}")

    def list_modes(self) -> list[str]:
        return sorted(self._factories)


default_registry = GameModeRegistry()
