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

from chess_core.ui.mode_picker import ModePicker, UiSession
from chess_core.core.gamemode import GameMode
from chess_core.core.registry import default_registry
from chess_core.ui.assets_loader import set_shogi_piece_set
from chess_core.ui.editor import EditorWidget
from chess_core.ui.experiments import EloDashboard
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.pgn_viewer import PgnViewerWidget
from chess_core.ui.theme import SHELL_STYLESHEET, app_icon, mode_display_name
from chess_core.ui.training.hub import TrainingHubWidget


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
        self.resize(1280, 720)
        self.setStyleSheet(SHELL_STYLESHEET)

        root = QWidget()
        root.setObjectName("rootPane")
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        mode_ids = list(mode_ids)
        rail = QWidget()
        rail.setObjectName("navRail")
        rail.setFixedWidth(268)
        sidebar = QVBoxLayout(rail)
        sidebar.setContentsMargins(12, 16, 12, 16)
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
        self._pgn_viewer = (
            PgnViewerWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        self._training = (
            TrainingHubWidget(mode_resolver, self.session.mode_id)
            if self.session.mode_id is not None
            else None
        )
        page_map = {
            "Локальная игра": self._local_game,
            "Просмотр PGN": self._pgn_viewer,
            "Редактор": self._editor,
            "Обучение": self._training,
            "Эксперименты Elo": EloDashboard(),
            "Задачи": self._make_placeholder("Задачи"),
        }
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for title, page in page_map.items():
            button = QPushButton(title)
            button.setCheckable(True)
            widget = page if page is not None else self._make_placeholder(title)
            index = self._stack.addWidget(widget)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self._stack.setCurrentIndex(page_index)
            )
            self._nav_group.addButton(button)
            self._nav_buttons[title] = button
            sidebar.addWidget(button)
        first = self._nav_buttons.get("Локальная игра")
        if first is not None:
            first.setChecked(True)
        if self._local_game is not None:
            picker.mode_changed.connect(self._local_game.set_mode)
        if self._pgn_viewer is not None:
            picker.mode_changed.connect(self._pgn_viewer.set_mode)
        if self._editor is not None:
            picker.mode_changed.connect(self._editor.set_mode)
            self._editor.play_requested.connect(self._start_from_editor)
        if self._training is not None:
            picker.mode_changed.connect(self._training.set_mode)
        picker.piece_set_changed.connect(self._on_piece_set_changed)
        picker.mode_changed.connect(self._on_mode_title)

        sidebar.addStretch()
        root_layout.addWidget(rail, 0)
        root_layout.addWidget(self._stack, 1)
        if self.session.mode_id is not None:
            self._on_mode_title(self.session.mode_id)

    def _on_mode_title(self, mode_id: str) -> None:
        self.setWindowTitle(f"Chess Core — {mode_display_name(mode_id)}")

    def _start_from_editor(self, state: object) -> None:
        if self._local_game is None:
            return
        self._local_game.load_position(state)
        self._stack.setCurrentWidget(self._local_game)
        local = self._nav_buttons.get("Локальная игра")
        if local is not None:
            local.setChecked(True)

    def _on_piece_set_changed(self, name: str) -> None:
        set_shogi_piece_set(name)
        if self._local_game is not None:
            self._local_game.reload_piece_assets()
        if self._editor is not None:
            self._editor.reload_piece_assets()
        if self._pgn_viewer is not None:
            self._pgn_viewer.reload_piece_assets()
        if self._training is not None:
            self._training.reload_piece_assets()

    def _make_placeholder(self, title: str) -> QLabel:
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label
