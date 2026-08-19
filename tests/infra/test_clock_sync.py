"""Tests for clock projection."""

from chess_core.app.clock import ClockSnapshot, GameClockService
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.clock_sync import ClockProjection


def test_projection_interpolates_running_side() -> None:
    service = GameClockService(TimeControlConfig.sudden_death(10), _Clock())
    snapshot = service.on_move_committed(PieceSide.WHITE, 0)
    projection = ClockProjection()
    projection.apply_snapshot(snapshot, client_mono_ms=1_000)
    display = projection.display_ms(PieceSide.BLACK, client_mono_ms=2_000)
    assert display < snapshot.black_remaining_ms


class _Clock:
    def now_ms(self) -> int:
        return 0
