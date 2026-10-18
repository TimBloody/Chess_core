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
    started: bool = False


class GameClockService:
    """Authoritative clock logic for local or server use."""

    def __init__(
        self,
        config: TimeControlConfig,
        clock: MonotonicClock,
        *,
        revision: int = 0,
        starting_side: PieceSide = PieceSide.WHITE,
    ) -> None:
        self._config = config
        self._clock = clock
        self._revision = revision
        self._state = _ClockState(
            white_ms=config.initial_ms[0],
            black_ms=config.initial_ms[1],
            white_byoyomi_left=config.byoyomi_periods,
            black_byoyomi_left=config.byoyomi_periods,
            running_side=starting_side,
            started_at_ms=None,
        )

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def config(self) -> TimeControlConfig:
        return self._config

    @property
    def is_paused(self) -> bool:
        return self._state.paused

    @property
    def has_started(self) -> bool:
        """True after the first committed turn; the clock is idle until then."""
        return self._state.started

    def reconfigure(
        self,
        config: TimeControlConfig,
        *,
        start_now: bool = False,
        running_side: PieceSide | None = None,
    ) -> ClockSnapshot:
        """Replace the control. ``start_now`` starts ticking for ``running_side``."""
        self._config = config
        self._state.white_ms = config.initial_ms[0]
        self._state.black_ms = config.initial_ms[1]
        self._state.white_byoyomi_left = config.byoyomi_periods
        self._state.black_byoyomi_left = config.byoyomi_periods
        if running_side is not None:
            self._state.running_side = running_side
        if config.kind is TimeControlKind.NONE:
            self._state.started = False
            self._state.started_at_ms = None
        elif start_now:
            self._state.started = True
            self._state.started_at_ms = None if self._state.paused else self._clock.now_ms()
        else:
            self._state.started = False
            self._state.started_at_ms = None
        self._revision += 1
        return self.snapshot()

    def snapshot(self) -> ClockSnapshot:
        """Read-only view. Remaining already includes elapsed; increment is not applied."""
        white_ms, black_ms = self._remaining_now()
        now = self._clock.now_ms()
        running = self._active_side()
        return ClockSnapshot(
            revision=self._revision,
            running_side=running,
            white_remaining_ms=white_ms,
            black_remaining_ms=black_ms,
            white_byoyomi_left=self._state.white_byoyomi_left,
            black_byoyomi_left=self._state.black_byoyomi_left,
            server_mono_ms=now,
            next_deadline_ms=self._compute_deadline(white_ms, black_ms, now),
            time_control=self._config,
        )

    def on_move_committed(self, side_that_moved: PieceSide, think_ms: int = 0) -> ClockSnapshot:
        think = self._elapsed_ms()
        if think > 0:
            self._apply_elapsed()
        else:
            think = max(0, think_ms)
            if think:
                self._consume_time(side_that_moved, think)
        self._grant_increment(side_that_moved, think)
        self._state.running_side = side_that_moved.opponent()
        self._state.started = True
        self._state.started_at_ms = None if self._state.paused else self._clock.now_ms()
        self._revision += 1
        return self.snapshot()

    def on_undo(self) -> ClockSnapshot:
        self._revision += 1
        return self.snapshot()

    def pause(self) -> ClockSnapshot:
        if self._state.paused:
            return self.snapshot()
        self._apply_elapsed()
        self._state.paused = True
        self._state.started_at_ms = None
        self._revision += 1
        return self.snapshot()

    def resume(self) -> ClockSnapshot:
        if not self._state.paused:
            return self.snapshot()
        self._state.paused = False
        if self._state.started and self._state.running_side is not None:
            self._state.started_at_ms = self._clock.now_ms()
        self._revision += 1
        return self.snapshot()

    def _active_side(self) -> PieceSide | None:
        if self._config.kind is TimeControlKind.NONE:
            return None
        if self._state.paused or not self._state.started:
            return None
        return self._state.running_side

    def _elapsed_ms(self) -> int:
        if self._active_side() is None:
            return 0
        if self._state.started_at_ms is None:
            return 0
        return max(0, self._clock.now_ms() - self._state.started_at_ms)

    def _remaining_now(self) -> tuple[int, int]:
        white_ms = self._state.white_ms
        black_ms = self._state.black_ms
        elapsed = self._elapsed_ms()
        if elapsed <= 0 or self._state.running_side is None:
            return white_ms, black_ms
        if self._state.running_side is PieceSide.WHITE:
            return _consumed(white_ms, elapsed), black_ms
        return white_ms, _consumed(black_ms, elapsed)

    def _apply_elapsed(self) -> None:
        elapsed = self._elapsed_ms()
        if elapsed <= 0 or self._state.running_side is None:
            return
        self._consume_time(self._state.running_side, elapsed)
        self._state.started_at_ms = self._clock.now_ms()

    def _consume_time(self, side: PieceSide, think_ms: int) -> None:
        if self._config.kind is TimeControlKind.BYOYOMI:
            self._consume_byoyomi(side, think_ms)
            return
        if side is PieceSide.WHITE:
            self._state.white_ms = _consumed(self._state.white_ms, think_ms)
        else:
            self._state.black_ms = _consumed(self._state.black_ms, think_ms)

    def _grant_increment(self, side: PieceSide, think_ms: int) -> None:
        config = self._config
        if config.kind is TimeControlKind.FISCHER:
            added = config.increment_ms
        elif config.kind is TimeControlKind.BRONSTEIN:
            added = min(config.increment_ms or config.delay_ms, think_ms)
        else:
            return
        if side is PieceSide.WHITE:
            self._state.white_ms += added
        else:
            self._state.black_ms += added

    def _consume_byoyomi(self, side: PieceSide, think_ms: int) -> None:
        if side is PieceSide.WHITE:
            if self._state.white_ms > 0:
                self._state.white_ms = _consumed(self._state.white_ms, think_ms)
                return
            if think_ms <= self._config.byoyomi_period_ms:
                return
            if self._state.white_byoyomi_left > 0:
                self._state.white_byoyomi_left -= 1
            return
        if self._state.black_ms > 0:
            self._state.black_ms = _consumed(self._state.black_ms, think_ms)
            return
        if think_ms <= self._config.byoyomi_period_ms:
            return
        if self._state.black_byoyomi_left > 0:
            self._state.black_byoyomi_left -= 1

    def _compute_deadline(self, white_ms: int, black_ms: int, now: int) -> int | None:
        if self._active_side() is None:
            return None
        remaining = white_ms if self._state.running_side is PieceSide.WHITE else black_ms
        if remaining <= 0 and self._config.kind is TimeControlKind.BYOYOMI:
            remaining = self._config.byoyomi_period_ms
        return now + remaining


def _consumed(remaining_ms: int, think_ms: int) -> int:
    return max(0, remaining_ms - think_ms)
