"""Main PyQt window for the initial UI shell."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.ui.mode_picker import ModePicker, UiSession
from chess_core.core.gamemode import GameMode
from chess_core.core.registry import default_registry
from chess_core.ui.editor import EditorWidget
from chess_core.ui.local_game import LocalGameWidget


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
        self.resize(1100, 720)

        root = QWidget()
        root_layout = QHBoxLayout()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        mode_ids = list(mode_ids)
        sidebar = QVBoxLayout()
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
        page_map = {
            "Локальная игра": self._local_game,
            "Редактор": self._editor,
            "Задачи": self._make_placeholder("Задачи"),
            "По памяти": self._make_placeholder("По памяти"),
        }
        for title, page in page_map.items():
            button = QPushButton(title)
            widget = page if page is not None else self._make_placeholder(title)
            index = self._stack.addWidget(widget)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self._stack.setCurrentIndex(page_index)
            )
            sidebar.addWidget(button)
        if self._local_game is not None:
            picker.mode_changed.connect(self._local_game.set_mode)
        if self._editor is not None:
            picker.mode_changed.connect(self._editor.set_mode)
            self._editor.play_requested.connect(self._start_from_editor)

        sidebar.addStretch()
        root_layout.addLayout(sidebar, 1)
        root_layout.addWidget(self._stack, 4)

    def _start_from_editor(self, state: object) -> None:
        if self._local_game is None:
            return
        self._local_game.load_position(state)
        self._stack.setCurrentWidget(self._local_game)

    def _make_placeholder(self, title: str) -> QLabel:
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label
