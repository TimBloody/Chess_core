"""Hand & Brain: classic chess with Brain/Hand roles on the match layer."""

from __future__ import annotations

from chess_core.core.gamemode import GameMode
from chess_core.modes.chess import _chess_mode


def hand_and_brain() -> GameMode:
    return _chess_mode(
        "hand_and_brain",
        "Hand & Brain",
        extras={"match_kind": "hand_and_brain"},
    )
