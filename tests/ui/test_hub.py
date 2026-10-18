"""Hub stays light until a branch is opened."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.ui.hub import HubWindow

_APP: QApplication | None = None
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_hub_window_has_five_branch_buttons() -> None:
    _app()
    window = HubWindow()
    assert window.local_button.text() == "Локальная игра"
    assert window.server_button.text() == "Сетевая игра"
    assert window.education_button.text() == "Обучение"
    assert window.tournament_button.text() == "Турнир"
    assert window.experiments_button.text() == "Эксперименты"
    assert window.theme_button.objectName() == "themeToggle"
    window.close()


def test_hub_window_toggles_fullscreen() -> None:
    _app()
    window = HubWindow()
    window.show()
    assert not window.isFullScreen()
    assert not window._fullscreen_escape.isEnabled()
    window.toggle_fullscreen()
    assert window.isFullScreen()
    assert window._fullscreen_escape.isEnabled()
    window.exit_fullscreen()
    assert not window.isFullScreen()
    assert not window._fullscreen_escape.isEnabled()
    window.close()


def test_hub_import_does_not_load_play_or_gobblet() -> None:
    code = """
import sys
from chess_core.ui.hub import HubWindow
assert "chess_core.ui.local_game" not in sys.modules
assert "chess_core.ui.network_game" not in sys.modules
assert "chess_core.ui.tournament" not in sys.modules
assert "chess_core.ui.puzzles" not in sys.modules
assert "chess_core.modes.gobblet" not in sys.modules
assert "chess_core.app.gobblet_engine" not in sys.modules
assert HubWindow is not None
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
    )
    assert completed.returncode == 0, completed.stderr


def test_register_builtin_modes_does_not_import_gobblet_until_get() -> None:
    code = """
import sys
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
register_builtin_modes()
assert "chess_core.modes.gobblet" not in sys.modules
default_registry.get("gobblet")
assert "chess_core.modes.gobblet" in sys.modules
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_ROOT),
    )
    assert completed.returncode == 0, completed.stderr
