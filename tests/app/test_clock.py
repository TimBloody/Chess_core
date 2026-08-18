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


def test_fischer_adds_increment_after_move() -> None:
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
