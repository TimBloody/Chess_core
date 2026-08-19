"""Education mini-games: memory drills and piece mazes."""

from chess_core.app.training.maze import (
    MAZE_HERO_TYPES,
    MazeMoveResult,
    MazePuzzle,
    MazeSession,
    MazeStatus,
    generate_maze,
)
from chess_core.app.training.memory import (
    MemoryFormat,
    PositionMemoryService,
    SequenceMemoryService,
    SequencePrompt,
    ShapeMemoryService,
    ShapePrompt,
)

__all__ = [
    "MAZE_HERO_TYPES",
    "MazeMoveResult",
    "MazePuzzle",
    "MazeSession",
    "MazeStatus",
    "MemoryFormat",
    "PositionMemoryService",
    "SequenceMemoryService",
    "SequencePrompt",
    "ShapeMemoryService",
    "ShapePrompt",
    "generate_maze",
]
