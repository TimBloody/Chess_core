"""Puzzle catalog loaders."""

from chess_core.infra.storage.lichess_puzzles import (
    bundled_lichess_mini_path,
    load_lichess_puzzles,
)

__all__ = ["bundled_lichess_mini_path", "load_lichess_puzzles"]
