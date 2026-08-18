"""Path resolution for dev and frozen (PyInstaller) layouts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return app_root()
    return Path(__file__).resolve().parents[3]


def assets_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return project_root() / "assets"


def masks_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "chess_core" / "data" / "masks"
    return Path(__file__).resolve().parents[1] / "data" / "masks"


def engines_dir() -> Path:
    env = os.environ.get("CHESS_CORE_ENGINES_DIR")
    if env:
        return Path(env)
    return project_root().parent / "engines"


def config_dir() -> Path:
    return app_root() / "config"
