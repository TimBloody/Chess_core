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


def puzzles_dir() -> Path:
    """Bundled Lichess puzzle catalogs (CSV/JSON)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "chess_core" / "data" / "puzzles"
    return Path(__file__).resolve().parents[1] / "data" / "puzzles"


def engines_dir() -> Path:
    env = os.environ.get("CHESS_CORE_ENGINES_DIR")
    if env:
        return Path(env)
    local_public = project_root() / "engines" / "public"
    if local_public.is_dir():
        return local_public
    return project_root().parent / "engines"


def engine_search_roots() -> tuple[Path, ...]:
    """All locations that may contain engine binaries."""
    roots: list[Path] = []
    env = os.environ.get("CHESS_CORE_ENGINES_DIR")
    if env:
        roots.append(Path(env))
    roots.append(project_root() / "engines" / "public")
    roots.append(project_root() / "engines")
    roots.append(project_root().parent / "engines")
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve() if root.exists() else root
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(root)
    return tuple(unique)


def config_dir() -> Path:
    return app_root() / "config"
