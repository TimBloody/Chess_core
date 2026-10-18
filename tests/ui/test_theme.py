"""Dark / light shell theme and board-coordinate ink."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.hub import HubWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.theme import (
    LIGHT_STYLESHEET,
    SHELL_STYLESHEET,
    THEME_SHORTCUT,
    ThemeKind,
    apply_theme,
    current_theme,
    notation_ink,
    toggle_theme,
)
from chess_core.ui.widgets.board_widget import BoardWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(ThemeKind.DARK, persist=False)
    return _APP


def _restore_dark() -> None:
    apply_theme(ThemeKind.DARK, persist=False)


def test_toggle_theme_switches_app_stylesheet() -> None:
    app = _app()
    assert current_theme() is ThemeKind.DARK
    assert app.styleSheet() == SHELL_STYLESHEET
    assert toggle_theme(persist=False) is ThemeKind.LIGHT
    assert app.styleSheet() == LIGHT_STYLESHEET
    assert toggle_theme(persist=False) is ThemeKind.DARK
    assert app.styleSheet() == SHELL_STYLESHEET
    _restore_dark()


def test_hub_theme_button_and_shortcut() -> None:
    _app()
    window = HubWindow()
    assert window.theme_button.objectName() == "themeToggle"
    assert window.theme_button.text() == "Светлая"
    assert window._theme_shortcut.key().toString() == THEME_SHORTCUT
    window.theme_button.click()
    assert current_theme() is ThemeKind.LIGHT
    assert window.theme_button.text() == "Тёмная"
    window.toggle_theme()
    assert current_theme() is ThemeKind.DARK
    assert window.theme_button.text() == "Светлая"
    window.close()
    _restore_dark()


def test_branch_window_puts_theme_toggle_in_the_rail() -> None:
    _app()
    register_builtin_modes()
    from chess_core.ui.branches.local_play import LocalPlayWindow

    window = LocalPlayWindow(default_registry.list_modes(), UiSession("chess"))
    rail = window.theme_button.parent()
    assert rail is not None
    assert rail.objectName() == "navRail"
    assert window.theme_button.text() == "Светлая"
    window.close()
    _restore_dark()


def test_notation_ink_is_white_on_dark_and_dark_on_light() -> None:
    _app()
    board = BoardWidget()
    board.resize(240, 240)
    board_rect, cell_size = board._board_geometry()
    image = QImage(board.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)

    apply_theme(ThemeKind.DARK, persist=False)
    board._draw_coordinates(painter, board_rect, cell_size)
    assert painter.pen().color() == QColor(255, 255, 255)
    assert notation_ink() == QColor(255, 255, 255)

    apply_theme(ThemeKind.LIGHT, persist=False)
    board._draw_coordinates(painter, board_rect, cell_size)
    assert painter.pen().color() == QColor(36, 32, 28)
    painter.end()
    board.close()
    _restore_dark()
