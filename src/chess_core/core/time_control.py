"""Time control configuration (core, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TimeControlKind(Enum):
    NONE = auto()
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
        return cls.from_parts(
            TimeControlKind.FISCHER,
            main_minutes=minutes,
            extra_seconds=increment_seconds,
        )

    @classmethod
    def none(cls) -> TimeControlConfig:
        return cls(kind=TimeControlKind.NONE, initial_ms=(0, 0))

    @classmethod
    def sudden_death(cls, minutes: int = 10) -> TimeControlConfig:
        return cls.from_parts(TimeControlKind.SIMPLE, main_minutes=minutes)

    @property
    def is_timed(self) -> bool:
        return self.kind is not TimeControlKind.NONE

    @classmethod
    def from_parts(
        cls,
        kind: TimeControlKind,
        *,
        main_minutes: int = 0,
        extra_seconds: int = 0,
        byoyomi_periods: int = 1,
    ) -> TimeControlConfig:
        """Build a symmetric control from UI-facing minutes / extra seconds."""
        if kind is TimeControlKind.NONE:
            return cls.none()
        main_ms = max(0, int(main_minutes)) * 60_000
        extra_ms = max(0, int(extra_seconds)) * 1000
        if kind is TimeControlKind.SIMPLE:
            return cls(kind=kind, initial_ms=(main_ms, main_ms))
        if kind is TimeControlKind.FISCHER:
            return cls(kind=kind, initial_ms=(main_ms, main_ms), increment_ms=extra_ms)
        if kind is TimeControlKind.BRONSTEIN:
            return cls(
                kind=kind,
                initial_ms=(main_ms, main_ms),
                increment_ms=extra_ms,
                delay_ms=extra_ms,
            )
        if kind is TimeControlKind.BYOYOMI:
            return cls(
                kind=kind,
                initial_ms=(main_ms, main_ms),
                byoyomi_period_ms=extra_ms,
                byoyomi_periods=max(1, int(byoyomi_periods)),
            )
        raise ValueError(f"unsupported time control kind: {kind!r}")

    @property
    def main_minutes(self) -> int:
        return self.initial_ms[0] // 60_000

    @property
    def extra_seconds(self) -> int:
        if self.kind is TimeControlKind.BYOYOMI:
            return self.byoyomi_period_ms // 1000
        extra_ms = self.increment_ms or self.delay_ms
        return extra_ms // 1000
