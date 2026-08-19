"""Run the standalone Elo laboratory."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PyQt6.QtWidgets import QApplication, QMainWindow

from chess_core.ui.experiments import EloDashboard


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Chess Core — Лаборатория Elo")
    window.resize(1440, 900)
    window.setCentralWidget(EloDashboard())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
