"""Chess clock state machine (application layer, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig, TimeControlKind


@dataclass(frozen=True, slots=True)
class ClockSnapshot:
    revision: int
    running_side: PieceSide | None
    white_remaining_ms: int
    black_remaining_ms: int
    white_byoyomi_left: int
    black_byoyomi_left: int
    server_mono_ms: int
    next_deadline_ms: int | None
    time_control: TimeControlConfig


class MonotonicClock(Protocol):
    def now_ms(self) -> int:
        ...


@dataclass
class _ClockState:
    white_ms: int
    black_ms: int
    white_byoyomi_left: int
    black_byoyomi_left: int
    running_side: PieceSide | None
    started_at_ms: int | None
    paused: bool = False


class GameClockService:
    """Authoritative clock logic for local or server use."""

    def __init__(
        self,
        config: TimeControlConfig,
        clock: MonotonicClock,
        *,
        revision: int = 0,
    ) -> None:
        self._config = config
        self._clock = clock
        self._revision = revision
        self._state = _ClockState(
            white_ms=config.initial_ms[0],
            black_ms=config.initial_ms[1],
            white_byoyomi_left=config.byoyomi_periods,
            black_byoyomi_left=config.byoyomi_periods,
            running_side=PieceSide.WHITE,
            started_at_ms=clock.now_ms(),
        )

    @property
    def revision(self) -> int:
        return self._revision

    def snapshot(self) -> ClockSnapshot:
        self._apply_elapsed()
        return ClockSnapshot(
            revision=self._revision,
            running_side=self._state.running_side if not self._state.paused else None,
            white_remaining_ms=self._state.white_ms,
            black_remaining_ms=self._state.black_ms,
            white_byoyomi_left=self._state.white_byoyomi_left,
            black_byoyomi_left=self._state.black_byoyomi_left,
            server_mono_ms=self._clock.now_ms(),
            next_deadline_ms=self._compute_deadline(),
            time_control=self._config,
        )

    def on_move_committed(self, side_that_moved: PieceSide, think_ms: int) -> ClockSnapshot:
        self._apply_elapsed()
        self._deduct(side_that_moved, think_ms)
        self._state.running_side = (
            PieceSide.BLACK if side_that_moved is PieceSide.WHITE else PieceSide.WHITE
        )
        self._state.started_at_ms = self._clock.now_ms()
        self._revision += 1
        return self.snapshot()

    def on_undo(self) -> ClockSnapshot:
        self._revision += 1
        return self.snapshot()

    def pause(self) -> ClockSnapshot:
        self._apply_elapsed()
        self._state.paused = True
        self._state.started_at_ms = None
        self._revision += 1
        return self.snapshot()

    def resume(self) -> ClockSnapshot:
        if self._state.running_side is not None:
            self._state.started_at_ms = self._clock.now_ms()
        self._state.paused = False
        self._revision += 1
        return self.snapshot()

    def _apply_elapsed(self) -> None:
        if self._state.paused or self._state.running_side is None:
            return
        if self._state.started_at_ms is None:
            return
        elapsed = self._clock.now_ms() - self._state.started_at_ms
        if elapsed <= 0:
            return
        self._deduct(self._state.running_side, elapsed)
        self._state.started_at_ms = self._clock.now_ms()

    def _deduct(self, side: PieceSide, think_ms: int) -> None:
        config = self._config
        if config.kind is TimeControlKind.BYOYOMI:
            self._deduct_byoyomi(side, think_ms)
            return
        effective = think_ms
        if config.kind is TimeControlKind.BRONSTEIN:
            effective = max(0, think_ms - config.delay_ms)
        if side is PieceSide.WHITE:
            self._state.white_ms = max(0, self._state.white_ms - effective)
            if config.kind is TimeControlKind.FISCHER:
                self._state.white_ms += config.increment_ms
            elif config.kind is TimeControlKind.BRONSTEIN:
                self._state.white_ms += min(config.increment_ms, think_ms)
        else:
            self._state.black_ms = max(0, self._state.black_ms - effective)
            if config.kind is TimeControlKind.FISCHER:
                self._state.black_ms += config.increment_ms
            elif config.kind is TimeControlKind.BRONSTEIN:
                self._state.black_ms += min(config.increment_ms, think_ms)

    def _deduct_byoyomi(self, side: PieceSide, think_ms: int) -> None:
        if side is PieceSide.WHITE:
            if self._state.white_ms > 0:
                self._state.white_ms = max(0, self._state.white_ms - think_ms)
            else:
                remaining = config_period = self._config.byoyomi_period_ms - think_ms
                if remaining >= 0:
                    return
                if self._state.white_byoyomi_left > 0:
                    self._state.white_byoyomi_left -= 1
                else:
                    self._state.white_ms = 0
        else:
            if self._state.black_ms > 0:
                self._state.black_ms = max(0, self._state.black_ms - think_ms)
            else:
                remaining = self._config.byoyomi_period_ms - think_ms
                if remaining >= 0:
                    return
                if self._state.black_byoyomi_left > 0:
                    self._state.black_byoyomi_left -= 1
                else:
                    self._state.black_ms = 0

    def _compute_deadline(self) -> int | None:
        if self._state.paused or self._state.running_side is None:
            return None
        side = self._state.running_side
        remaining = self._state.white_ms if side is PieceSide.WHITE else self._state.black_ms
        if remaining <= 0 and self._config.kind is TimeControlKind.BYOYOMI:
            remaining = self._config.byoyomi_period_ms
        if self._state.started_at_ms is None:
            return None
        return self._state.started_at_ms + remaining
