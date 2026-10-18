"""Shared mode registration for play/education branches."""

from __future__ import annotations

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.mode_picker import UiSession


def prepared_mode_ids(session: UiSession | None = None) -> tuple[list[str], UiSession]:
    register_builtin_modes()
    mode_ids = default_registry.list_modes()
    resolved = session or UiSession()
    if resolved.mode_id is None and mode_ids:
        resolved.mode_id = mode_ids[0]
    return mode_ids, resolved
