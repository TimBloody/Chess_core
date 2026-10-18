"""Lightweight product hub: opens branch windows without importing them."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.ui.theme import FullscreenMainWindow, app_icon, tighten_wrapping_label


class HubWindow(FullscreenMainWindow):
    """Entry window. Branch modules load only when the matching button is used."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chess Core")
        self.setWindowIcon(app_icon())
        self.resize(520, 560)
        self._branches: dict[str, QMainWindow] = {}

        root = QWidget()
        root.setObjectName("hubPane")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(12)

        title = QLabel("Chess Core")
        title.setObjectName("hubTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Выберите раздел. Остальные ветки не загружаются, пока вы в них не зайдёте.")
        subtitle.setObjectName("gameHint")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tighten_wrapping_label(subtitle)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        self.local_button = self._add_button(layout, "Локальная игра", self._open_local)
        self.server_button = self._add_button(layout, "Сетевая игра", self._open_server)
        self.education_button = self._add_button(layout, "Обучение", self._open_education)
        self.tournament_button = self._add_button(layout, "Турнир", self._open_tournament)
        self.experiments_button = self._add_button(layout, "Эксперименты", self._open_experiments)
        layout.addStretch()
        theme_row = QHBoxLayout()
        theme_row.addStretch()
        theme_row.addWidget(self.theme_button)
        layout.addLayout(theme_row)
        self.setCentralWidget(root)

    def closeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        for window in list(self._branches.values()):
            window.close()
        self._branches.clear()
        super().closeEvent(event)

    def _add_button(self, layout: QVBoxLayout, title: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(title)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def _open_local(self) -> None:
        from chess_core.ui.branches.local_play import LocalPlayWindow

        self._open_branch("local", LocalPlayWindow)

    def _open_server(self) -> None:
        from chess_core.ui.branches.server_play import ServerPlayWindow

        self._open_branch("server", ServerPlayWindow)

    def _open_education(self) -> None:
        from chess_core.ui.branches.education import EducationWindow

        self._open_branch("education", EducationWindow)

    def _open_tournament(self) -> None:
        from chess_core.ui.branches.tournament import TournamentWindow

        self._open_branch("tournament", TournamentWindow)

    def _open_experiments(self) -> None:
        from chess_core.ui.branches.experiments import ExperimentsWindow

        self._open_branch("experiments", ExperimentsWindow)

    def _open_branch(self, key: str, factory: Callable[[], QMainWindow]) -> None:
        existing = self._branches.get(key)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        window = factory()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        window.destroyed.connect(lambda _obj=None, branch=key: self._branches.pop(branch, None))
        self._branches[key] = window
        window.show()
