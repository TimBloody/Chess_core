import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.network_game import NetworkGameWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_network_page_is_in_shell() -> None:
    _app()
    register_builtin_modes()
    window = MainWindow(default_registry.list_modes(), UiSession("chess"))
    assert "Сеть" in window._nav_buttons
    assert isinstance(window._network_game, NetworkGameWidget)
    window._nav_buttons["Сеть"].click()
    assert window._stack.currentWidget() is window._network_game
    window.close()
