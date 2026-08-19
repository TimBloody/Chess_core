"""Education hub with memorisation and maze mini-games."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.core.gamemode import GameMode
from chess_core.core.registry import default_registry
from chess_core.ui.training.maze_widget import MazeTrainingWidget
from chess_core.ui.training.memory_widget import MemoryTrainingWidget


class TrainingHubWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        mode_id: str = "chess",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.memory = MemoryTrainingWidget(mode_resolver, mode_id)
        self.maze = MazeTrainingWidget(mode_resolver)
        self._stack = QStackedWidget()
        self._stack.addWidget(self.memory)
        self._stack.addWidget(self.maze)

        self.memory_button = QPushButton("Запоминание")
        self.maze_button = QPushButton("Лабиринт")
        self.memory_button.setCheckable(True)
        self.maze_button.setCheckable(True)
        self.memory_button.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.memory_button)
        group.addButton(self.maze_button)

        intro = QLabel("Учебные мини-игры: память и ходы фигур.")
        intro.setObjectName("panelTitle")
        tabs = QHBoxLayout()
        tabs.addWidget(self.memory_button)
        tabs.addWidget(self.maze_button)
        tabs.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(tabs)
        layout.addWidget(self._stack, 1)

        self.memory_button.clicked.connect(lambda: self._stack.setCurrentWidget(self.memory))
        self.maze_button.clicked.connect(lambda: self._stack.setCurrentWidget(self.maze))

    def set_mode(self, mode_id: str) -> None:
        self.memory.set_mode(mode_id)

    def reload_piece_assets(self) -> None:
        self.memory.reload_piece_assets()
        self.maze.reload_piece_assets()
