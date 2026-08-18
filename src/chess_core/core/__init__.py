"""Core rules, board, topology, and move generation (no UI/network)."""

from chess_core.core.board import Board, BoardShape, Square
from chess_core.core.gamemode import GameMode, GameModeBuilder

__all__ = [
    "Board",
    "BoardShape",
    "Square",
    "GameMode",
    "GameModeBuilder",
]
