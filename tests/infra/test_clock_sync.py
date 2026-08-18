"""Tests for clock projection."""

from chess_core.app.clock import ClockSnapshot, GameClockService
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.clock_sync import ClockProjection


def test_projection_interpolates_running_side() -> None:
    service = GameClockService(TimeControlConfig.sudden_death(10), _Clock())
    snapshot = service.snapshot()
    projection = ClockProjection()
    projection.apply_snapshot(snapshot, client_mono_ms=1_000)
    display = projection.display_ms(PieceSide.WHITE, client_mono_ms=2_000)
    assert display < snapshot.white_remaining_ms


class _Clock:
    def now_ms(self) -> int:
        return 0
