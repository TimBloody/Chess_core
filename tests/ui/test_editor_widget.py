"""Offscreen editor widget smoke tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.modes import register_builtin_modes
from chess_core.ui.editor import EditorWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_editor_widget_loads_start_position() -> None:
    _app()
    register_builtin_modes()
    widget = EditorWidget(mode_id="chess")
    widget._load_start()
    assert len(widget.board.position) == 32
    widget._play()
    widget.close()
