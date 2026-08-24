"""Executable entry point for the PyQt UI shell."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.theme import SHELL_STYLESHEET, app_icon


def main() -> int:
    register_builtin_modes()
    mode_ids = default_registry.list_modes() or []

    app = QApplication(sys.argv)
    app.setStyleSheet(SHELL_STYLESHEET)
    app.setWindowIcon(app_icon())
    window = MainWindow(mode_ids=mode_ids, session=UiSession())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
