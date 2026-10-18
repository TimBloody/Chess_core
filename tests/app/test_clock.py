"""Tests for chess clock service."""

from chess_core.app.clock import GameClockService
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig, TimeControlKind


class FakeClock:
    def __init__(self) -> None:
        self._now = 0

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        self._now += ms


def test_clock_does_not_tick_until_first_move() -> None:
    clock = FakeClock()
    service = GameClockService(
        TimeControlConfig(
            kind=TimeControlKind.FISCHER,
            initial_ms=(60_000, 60_000),
            increment_ms=2_000,
        ),
        clock,
    )
    clock.advance(8_000)
    idle = service.snapshot()
    assert not service.has_started
    assert idle.running_side is None
    assert idle.white_remaining_ms == 60_000
    assert idle.black_remaining_ms == 60_000
    assert idle.next_deadline_ms is None

    started = service.on_move_committed(PieceSide.WHITE, 0)
    assert service.has_started
    assert started.running_side is PieceSide.BLACK
    assert started.white_remaining_ms == 62_000
    assert started.black_remaining_ms == 60_000
    clock.advance(3_000)
    ticking = service.snapshot()
    assert ticking.black_remaining_ms == 57_000
    assert ticking.white_remaining_ms == 62_000


def test_elapsed_time_decreases_remaining_without_fischer_increment() -> None:
    clock = FakeClock()
    service = GameClockService(
        TimeControlConfig(
            kind=TimeControlKind.FISCHER,
            initial_ms=(60_000, 60_000),
            increment_ms=2_000,
        ),
        clock,
    )
    service.on_move_committed(PieceSide.WHITE, 0)
    clock.advance(3_000)
    snapshot = service.snapshot()
    assert snapshot.black_remaining_ms == 57_000
    clock.advance(1_000)
    later = service.snapshot()
    assert later.black_remaining_ms == 56_000
    assert later.black_remaining_ms < snapshot.black_remaining_ms
    assert later.white_remaining_ms == 62_000


def test_pause_freezes_remaining_and_is_idempotent() -> None:
    clock = FakeClock()
    service = GameClockService(
        TimeControlConfig.sudden_death(1),
        clock,
    )
    service.on_move_committed(PieceSide.WHITE, 0)
    clock.advance(4_000)
    paused = service.pause()
    assert service.is_paused
    assert paused.running_side is None
    assert paused.black_remaining_ms == 56_000
    clock.advance(10_000)
    still = service.pause()
    assert still.black_remaining_ms == 56_000
    assert still.white_remaining_ms == 60_000
    resumed = service.resume()
    assert not service.is_paused
    assert resumed.running_side is PieceSide.BLACK
    clock.advance(2_000)
    assert service.snapshot().black_remaining_ms == 54_000


def test_resume_before_first_move_does_not_start_the_clock() -> None:
    clock = FakeClock()
    service = GameClockService(TimeControlConfig.sudden_death(1), clock)
    service.pause()
    service.resume()
    clock.advance(5_000)
    snapshot = service.snapshot()
    assert not service.has_started
    assert snapshot.running_side is None
    assert snapshot.white_remaining_ms == 60_000


def test_fischer_adds_increment_only_after_move() -> None:
    clock = FakeClock()
    service = GameClockService(
        TimeControlConfig(
            kind=TimeControlKind.FISCHER,
            initial_ms=(60_000, 60_000),
            increment_ms=2_000,
        ),
        clock,
    )
    snapshot = service.on_move_committed(PieceSide.WHITE, 1_000)
    assert snapshot.white_remaining_ms == 61_000
    assert snapshot.running_side is PieceSide.BLACK


def test_byoyomi_snapshot_exposes_periods() -> None:
    service = GameClockService(
        TimeControlConfig(
            kind=TimeControlKind.BYOYOMI,
            initial_ms=(0, 0),
            byoyomi_period_ms=30_000,
            byoyomi_periods=3,
        ),
        FakeClock(),
    )
    snapshot = service.snapshot()
    assert snapshot.white_byoyomi_left == 3
    assert snapshot.running_side is None


def test_reconfigure_before_start_replaces_remaining() -> None:
    clock = FakeClock()
    service = GameClockService(TimeControlConfig.blitz(), clock)
    updated = service.reconfigure(
        TimeControlConfig.from_parts(
            TimeControlKind.BRONSTEIN,
            main_minutes=10,
            extra_seconds=5,
        )
    )
    assert service.config.kind is TimeControlKind.BRONSTEIN
    assert updated.white_remaining_ms == 600_000
    assert updated.black_remaining_ms == 600_000
    assert not service.has_started


def test_reconfigure_after_first_move_resets_remaining() -> None:
    service = GameClockService(TimeControlConfig.blitz(), FakeClock())
    service.on_move_committed(PieceSide.WHITE, 0)
    updated = service.reconfigure(TimeControlConfig.sudden_death(5))
    assert service.config.kind is TimeControlKind.SIMPLE
    assert updated.white_remaining_ms == 300_000
    assert not service.has_started


def test_reconfigure_to_none_stops_ticking() -> None:
    clock = FakeClock()
    service = GameClockService(TimeControlConfig.blitz(), clock)
    service.on_move_committed(PieceSide.WHITE, 0)
    clock.advance(2_000)
    service.reconfigure(TimeControlConfig.none())
    clock.advance(8_000)
    snapshot = service.snapshot()
    assert not service.config.is_timed
    assert snapshot.running_side is None
    assert snapshot.next_deadline_ms is None


def test_reconfigure_start_now_ticks_current_side() -> None:
    clock = FakeClock()
    service = GameClockService(TimeControlConfig.none(), clock)
    service.reconfigure(
        TimeControlConfig.sudden_death(1),
        start_now=True,
        running_side=PieceSide.BLACK,
    )
    clock.advance(4_000)
    snapshot = service.snapshot()
    assert service.has_started
    assert snapshot.running_side is PieceSide.BLACK
    assert snapshot.black_remaining_ms == 56_000
