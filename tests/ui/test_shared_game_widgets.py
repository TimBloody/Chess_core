"""Tests for shared game widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel

from chess_core.app.clock import ClockSnapshot, GameClockService
from chess_core.app.engine import EngineEvaluation
from chess_core.core.time_control import TimeControlConfig
from chess_core.ui.sound_player import SoundPlayer
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget, PlayerClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketStack, PocketWidget
from chess_core.app.sound import SoundEvent
from chess_core.core.piece import PieceSide
from chess_core.infra.paths import sounds_dir

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_move_list_emits_revision() -> None:
    _app()
    widget = MoveListWidget()
    widget.set_moves(["1. e4  e5"], live_revision=1, view_revision=1)
    assert widget.count() == 1


def test_clock_widget_formats_snapshot() -> None:
    _app()
    widget = GameClockWidget()
    service = GameClockService(TimeControlConfig.sudden_death(5), _Clock())
    widget.set_snapshot(service.snapshot())
    assert ":" in widget._white.text()


def test_evaluation_bar_shows_cp() -> None:
    _app()
    widget = EvaluationBarWidget()
    widget.set_evaluation(EngineEvaluation(score_cp=35, mate_in=None, pv=("e2e4",)))
    assert "+0.3" in widget._bar.text()
    assert widget._white_share > 0.5


def test_evaluation_bar_shows_error() -> None:
    _app()
    widget = EvaluationBarWidget()
    widget.set_evaluation(None, error="Нет подходящего движка")
    assert widget._bar.text() == "—"
    assert "Нет подходящего" in widget._detail.text()


def test_player_clock_warns_when_low_on_time() -> None:
    _app()
    widget = PlayerClockWidget(PieceSide.WHITE)
    snapshot = ClockSnapshot(
        revision=1,
        running_side=PieceSide.WHITE,
        white_remaining_ms=8_000,
        black_remaining_ms=60_000,
        white_byoyomi_left=0,
        black_byoyomi_left=0,
        server_mono_ms=0,
        next_deadline_ms=None,
        time_control=TimeControlConfig.blitz(),
    )
    widget.apply_snapshot(snapshot, client_mono_ms=0)
    assert "#b03030" in widget.styleSheet().lower()


def test_clock_widget_counts_down_fischer_remaining() -> None:
    _app()
    widget = GameClockWidget()
    clock = _AdvancingClock()
    service = GameClockService(TimeControlConfig.blitz(), clock)
    service.on_move_committed(PieceSide.WHITE, 0)
    first = service.snapshot()
    widget.set_snapshot(first, client_mono_ms=clock.now_ms())
    shown_before = widget._black.text()
    clock.advance(5_000)
    later = service.snapshot()
    widget.set_snapshot(later, client_mono_ms=clock.now_ms())
    assert later.black_remaining_ms < first.black_remaining_ms
    assert widget._black.text() != shown_before


class _Clock:
    def now_ms(self) -> int:
        return 0


class _AdvancingClock:
    def __init__(self) -> None:
        self._now = 0

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        self._now += ms


def test_pocket_widget_miniatures_have_no_name_labels() -> None:
    _app()
    widget = PocketWidget(PieceSide.WHITE)
    widget.set_capacity(5)
    widget.set_stacks((PocketStack("wN", "knight", 2), PocketStack("wP", "pawn", 1)))
    widget.set_interactive(True)
    widget.resize(widget.sizeHint())
    assert widget.findChildren(QLabel) == []
    assert widget.sizeHint().width() >= 5 * 36
    clicked: list[str] = []
    widget.piece_clicked.connect(clicked.append)
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(26, 26))
    assert clicked == ["knight"]


def test_pocket_komadai_is_square_grid() -> None:
    _app()
    widget = PocketWidget(PieceSide.BLACK)
    widget.set_capacity(7)
    widget.set_grid(True, columns=3)
    hint = widget.sizeHint()
    assert widget.is_grid
    assert hint.width() == hint.height()
    assert hint.width() >= 3 * 40


def test_player_clock_is_large() -> None:
    _app()
    widget = PlayerClockWidget(PieceSide.WHITE)
    assert widget._time.font().pixelSize() >= 28
    assert widget.minimumHeight() >= 72


def test_black_player_clock_keeps_light_text_on_dark_background() -> None:
    _app()
    widget = PlayerClockWidget(PieceSide.BLACK)
    widget.apply_snapshot(GameClockService(TimeControlConfig.blitz(), _Clock()).snapshot())
    style = widget.styleSheet()
    assert "#f5f5f5" in style.lower()
    assert "PlayerClockWidget QLabel" in style
    assert ":" in widget._time.text()


def test_sound_catalog_and_missing_files_are_safe() -> None:
    names = {event.filename for event in SoundEvent}
    assert "drop.wav" in names
    assert "move.wav" in names
    assert sounds_dir().is_dir()
    SoundPlayer().play(SoundEvent.MOVE, accent=SoundEvent.CHECK)
