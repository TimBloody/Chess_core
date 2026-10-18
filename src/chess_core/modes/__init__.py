"""Register built-in mode factories without importing every ruleset up front."""

from __future__ import annotations

import importlib

from chess_core.core.gamemode import GameMode
from chess_core.core.registry import default_registry

_REGISTERED = False

_MODE_FACTORIES: tuple[tuple[str, str, str], ...] = (
    ("chess", "chess_core.modes.chess", "classic_chess"),
    ("chess960", "chess_core.modes.chess", "chess960"),
    ("crazyhouse", "chess_core.modes.chess", "crazyhouse"),
    ("bughouse", "chess_core.modes.bughouse", "bughouse"),
    ("hand_and_brain", "chess_core.modes.hand_and_brain", "hand_and_brain"),
    ("giveaway", "chess_core.modes.chess", "giveaway"),
    ("minichess", "chess_core.modes.chess", "minichess"),
    ("cylindrical", "chess_core.modes.chess", "cylindrical_chess"),
    ("duck", "chess_core.modes.chess", "duck_chess"),
    ("shogi", "chess_core.modes.shogi", "shogi"),
    ("kyoto_shogi", "chess_core.modes.shogi", "kyoto_shogi"),
    ("dobutsu_shogi", "chess_core.modes.shogi", "dobutsu_shogi"),
    ("hasami_shogi", "chess_core.modes.hasami_shogi", "hasami_shogi"),
    ("reversi", "chess_core.modes.board_games", "reversi"),
    ("corners", "chess_core.modes.board_games", "corners"),
    ("draughts", "chess_core.modes.board_games", "draughts"),
    ("nanai_checkers", "chess_core.modes.nanai_checkers", "nanai_checkers"),
    ("gobblet", "chess_core.modes.gobblet", "gobblet"),
)


def _lazy_factory(module: str, attr: str):
    def factory():
        return getattr(importlib.import_module(module), attr)()

    factory.__name__ = attr
    factory.__qualname__ = f"{module}.{attr}"
    return factory


def register_builtin_modes() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    for mode_id, module, attr in _MODE_FACTORIES:
        default_registry.register(mode_id, _lazy_factory(module, attr))
    _REGISTERED = True


def resolve_mode(mode_id: str) -> GameMode:
    """Preset factory, or a composed ``base+layer`` id from the orchestrator."""
    register_builtin_modes()
    try:
        return default_registry.get(mode_id)
    except KeyError:
        from chess_core.modes.orchestrator import compose_mode

        try:
            return compose_mode(mode_id)
        except ValueError as exc:
            raise KeyError(f"unknown game mode: {mode_id}") from exc
