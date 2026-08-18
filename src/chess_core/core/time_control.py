"""Time control configuration (core, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TimeControlKind(Enum):
    SIMPLE = auto()
    FISCHER = auto()
    BRONSTEIN = auto()
    BYOYOMI = auto()


@dataclass(frozen=True, slots=True)
class TimeControlConfig:
    kind: TimeControlKind
    initial_ms: tuple[int, int]
    increment_ms: int = 0
    delay_ms: int = 0
    byoyomi_period_ms: int = 0
    byoyomi_periods: int = 0

    @classmethod
    def blitz(cls, minutes: int = 3, increment_seconds: int = 2) -> TimeControlConfig:
        ms = minutes * 60_000
        return cls(
            kind=TimeControlKind.FISCHER,
            initial_ms=(ms, ms),
            increment_ms=increment_seconds * 1000,
        )

    @classmethod
    def sudden_death(cls, minutes: int = 10) -> TimeControlConfig:
        ms = minutes * 60_000
        return cls(kind=TimeControlKind.SIMPLE, initial_ms=(ms, ms))
