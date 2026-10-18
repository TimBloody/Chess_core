"""Executable entry point: hub only. Branches load on demand."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from chess_core.ui.hub import HubWindow
from chess_core.ui.theme import apply_saved_theme, app_icon


def main() -> int:
    app = QApplication(sys.argv)
    apply_saved_theme()
    app.setWindowIcon(app_icon())
    window = HubWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
