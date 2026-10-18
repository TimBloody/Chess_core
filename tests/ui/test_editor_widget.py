"""Offscreen editor widget smoke tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.modes import register_builtin_modes
from chess_core.ui.editor import EditorWidget
from chess_core.ui.widgets.editor_palette import EditorPaletteStrip

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
    assert isinstance(widget.white_palette, EditorPaletteStrip)
    assert widget.white_palette.tokens
    assert all(token.piece_key for token in widget.white_palette.tokens)
    assert widget.play_button.text() == "Играть с позиции"
    assert widget.white_to_move_button.isChecked()
    widget.black_to_move_button.click()
    assert widget.current_state().side_to_move.name == "BLACK"
    widget._play()
    widget.close()


def test_editor_widget_uses_custom_play_button_text() -> None:
    _app()
    register_builtin_modes()
    widget = EditorWidget(mode_id="chess", play_button_text="Анализировать позицию")
    assert widget.play_button.text() == "Анализировать позицию"
    widget.close()
