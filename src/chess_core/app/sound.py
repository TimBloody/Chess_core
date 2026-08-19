"""Sound event catalog. UI plays files; missing clips are skipped."""

from __future__ import annotations

from enum import Enum


class SoundEvent(Enum):
    """Short SFX keyed to ``assets/sounds/{value}.wav``."""

    GAME_START = "game_start"
    MOVE = "move"
    CAPTURE = "capture"
    CASTLE = "castle"
    DROP = "drop"
    PROMOTE = "promote"
    DUCK = "duck"
    CHECK = "check"
    CHECKMATE = "checkmate"
    STALEMATE = "stalemate"
    VARIANT_WIN = "variant_win"
    ILLEGAL = "illegal"
    UNDO = "undo"

    @property
    def filename(self) -> str:
        return f"{self.value}.wav"
