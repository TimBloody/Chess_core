from chess_core.core.time_control import TimeControlConfig, TimeControlKind


def test_from_parts_builds_fischer_minutes_and_increment() -> None:
    config = TimeControlConfig.from_parts(
        TimeControlKind.FISCHER,
        main_minutes=5,
        extra_seconds=3,
    )
    assert config.kind is TimeControlKind.FISCHER
    assert config.initial_ms == (300_000, 300_000)
    assert config.increment_ms == 3_000
    assert config.main_minutes == 5
    assert config.extra_seconds == 3


def test_from_parts_bronstein_uses_extra_as_delay() -> None:
    config = TimeControlConfig.from_parts(
        TimeControlKind.BRONSTEIN,
        main_minutes=10,
        extra_seconds=5,
    )
    assert config.kind is TimeControlKind.BRONSTEIN
    assert config.increment_ms == 5_000
    assert config.delay_ms == 5_000
    assert config.extra_seconds == 5


def test_from_parts_byoyomi_uses_extra_as_period() -> None:
    config = TimeControlConfig.from_parts(
        TimeControlKind.BYOYOMI,
        main_minutes=10,
        extra_seconds=30,
        byoyomi_periods=3,
    )
    assert config.kind is TimeControlKind.BYOYOMI
    assert config.initial_ms == (600_000, 600_000)
    assert config.byoyomi_period_ms == 30_000
    assert config.byoyomi_periods == 3
    assert config.extra_seconds == 30


def test_blitz_is_fischer_from_parts() -> None:
    config = TimeControlConfig.blitz(3, 2)
    assert config.kind is TimeControlKind.FISCHER
    assert config.main_minutes == 3
    assert config.extra_seconds == 2


def test_none_is_untimed() -> None:
    config = TimeControlConfig.none()
    assert config.kind is TimeControlKind.NONE
    assert not config.is_timed
    assert TimeControlConfig.from_parts(TimeControlKind.NONE).kind is TimeControlKind.NONE
