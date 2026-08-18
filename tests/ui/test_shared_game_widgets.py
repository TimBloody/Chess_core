"""Tests for shared game widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.clock import GameClockService
from chess_core.app.engine import EngineEvaluation
from chess_core.core.time_control import TimeControlConfig
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget

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


class _Clock:
    def now_ms(self) -> int:
        return 0
