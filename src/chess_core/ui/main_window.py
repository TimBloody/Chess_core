"""Main PyQt window for the initial UI shell."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.core.gamemode import GameMode
from chess_core.core.registry import default_registry
from chess_core.ui.editor import EditorWidget
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.mode_picker import ModePicker, UiSession
from chess_core.ui.network_game import NetworkGameWidget
from chess_core.ui.puzzles import PuzzleWidget
from chess_core.ui.theme import app_icon
from chess_core.ui.tournament import TournamentWidget
from chess_core.ui.training.memory_widget import MemoryTrainingWidget


class MainWindow(QMainWindow):
    """Top-level shell: mode picker, navigation buttons, and placeholders."""

    def __init__(
        self,
        mode_ids: Iterable[str],
        session: UiSession | None = None,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session or UiSession()
        self.setWindowTitle("Chess Core")
        self.setWindowIcon(app_icon())
        self.resize(1100, 720)

        root = QWidget()
        root.setObjectName("rootPane")
        root_layout = QHBoxLayout()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        mode_ids = list(mode_ids)
        if self.session.mode_id is None and mode_ids:
            self.session.mode_id = mode_ids[0]
        rail = QWidget()
        rail.setObjectName("navRail")
        sidebar = QVBoxLayout(rail)
        picker = ModePicker(mode_ids, self.session)
        sidebar.addWidget(picker)
        sidebar.addSpacing(12)

        self._stack = QStackedWidget()
        self._local_game = (
            LocalGameWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        self._editor = (
            EditorWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        self._network_game = (
            NetworkGameWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        self._puzzles = PuzzleWidget()
        self._memory = (
            MemoryTrainingWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        page_map = {
            "Локальная игра": self._local_game,
            "Сеть": self._network_game,
            "Редактор": self._editor,
            "Жеребьёвка": TournamentWidget(),
            "Задачи": self._puzzles,
            "По памяти": self._memory,
        }
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for title, page in page_map.items():
            button = QPushButton(title)
            button.setCheckable(True)
            widget = page if page is not None else self._make_placeholder(title)
            index = self._stack.addWidget(widget)
            self._nav_group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self._stack.setCurrentIndex(page_index)
            )
            sidebar.addWidget(button)
            if index == 0:
                button.setChecked(True)
        if self._local_game is not None:
            picker.mode_changed.connect(self._local_game.set_mode)
        if self._network_game is not None:
            picker.mode_changed.connect(self._network_game.set_mode)
        if self._editor is not None:
            picker.mode_changed.connect(self._editor.set_mode)
            self._editor.play_requested.connect(self._start_from_editor)
        if self._memory is not None:
            picker.mode_changed.connect(self._memory.set_mode)

        sidebar.addStretch()
        root_layout.addWidget(rail, 1)
        root_layout.addWidget(self._stack, 4)

    def _start_from_editor(self, state: object) -> None:
        if self._local_game is None:
            return
        self._local_game.load_position(state)
        self._stack.setCurrentWidget(self._local_game)

    def _make_placeholder(self, title: str) -> QLabel:
        label = QLabel(title)
        label.setObjectName("gameStatus")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label
