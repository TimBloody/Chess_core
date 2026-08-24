"""Launch a two-sided local game of classical chess in PyQt6."""

from __future__ import annotations

import sys
from pathlib import Path

# Make the root-level launcher work even before an editable package install.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PyQt6.QtWidgets import QApplication, QMainWindow

from chess_core.modes.chess import classic_chess
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.theme import SHELL_STYLESHEET, app_icon


class ClassicGameWindow(QMainWindow):
    """Small dedicated window for local classical chess."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chess Core — Классические шахматы")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(SHELL_STYLESHEET)
        self.resize(1000, 780)
        self.game = LocalGameWidget(lambda _mode_id: classic_chess(), "chess")
        self.setCentralWidget(self.game)


def create_window() -> ClassicGameWindow:
    """Construct the window; a QApplication must already exist."""

    if QApplication.instance() is None:
        raise RuntimeError("Create QApplication before creating the chess window")
    return ClassicGameWindow()


def main() -> int:
    app = QApplication(sys.argv)
    window = create_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
