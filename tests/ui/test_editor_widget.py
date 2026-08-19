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


def test_editor_dobutsu_uses_svg_palette_and_does_not_crash_on_click() -> None:
    app = _app()
    register_builtin_modes()
    widget = EditorWidget(mode_id="chess")
    widget.set_mode("dobutsu_shogi")
    assert widget.board.files == 3
    assert widget.board.ranks == 4
    assert widget._selected_piece is not None
    assert widget._selected_piece[0] in {"chick", "lion", "giraffe", "elephant", "hen"}
    assert any(key.startswith("dobutsu/0OU") for key in widget.board.position.values())
    assert widget.bottom_palette.tokens
    assert all(
        token.piece_key.startswith("dobutsu/")
        for token in widget.bottom_palette.tokens
    )
    widget.resize(900, 640)
    widget.show()
    app.processEvents()
    widget._on_square(0)
    app.processEvents()
    assert 0 in widget.board.position
    widget._erase_square(0)
    widget._export_fen()
    assert widget.fen_field.text()
    widget.close()
