"""Mode selection widgets for the PyQt UI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget


@dataclass
class UiSession:
    """Small mutable UI session shared by shell widgets."""

    mode_id: str | None = None


class ModePicker(QWidget):
    """Pick a registered game mode and store it in ``UiSession``."""

    mode_changed = pyqtSignal(str)

    def __init__(
        self,
        mode_ids: Iterable[str],
        session: UiSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._mode_ids = list(mode_ids)

        title = QLabel("Режим")
        self._combo = QComboBox()
        self._status = QLabel()

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self._combo)
        layout.addWidget(self._status)
        self.setLayout(layout)

        for mode_id in self._mode_ids:
            self._combo.addItem(mode_id, mode_id)

        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        self._select_initial_mode()

    @property
    def selected_mode_id(self) -> str | None:
        return self._session.mode_id

    def _select_initial_mode(self) -> None:
        if not self._mode_ids:
            self._combo.setEnabled(False)
            self._status.setText("Нет зарегистрированных режимов")
            self._session.mode_id = None
            return

        initial_index = 0
        if self._session.mode_id in self._mode_ids:
            initial_index = self._mode_ids.index(self._session.mode_id)

        self._combo.setCurrentIndex(initial_index)
        self._set_session_mode(initial_index)

    def _on_mode_changed(self, index: int) -> None:
        mode_id = self._set_session_mode(index)
        if mode_id is not None:
            self.mode_changed.emit(mode_id)

    def _set_session_mode(self, index: int) -> str | None:
        mode_id = self._combo.itemData(index)
        if mode_id is None:
            return None

        self._session.mode_id = str(mode_id)
        self._status.setText(f"Выбран: {self._session.mode_id}")
        return self._session.mode_id
