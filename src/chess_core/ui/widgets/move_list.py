"""Move list sidebar widget (presentation only)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


class MoveListWidget(QListWidget):
    revision_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._live_revision = 0
        self._view_revision = 0
        self.itemClicked.connect(self._on_item_clicked)

    def set_moves(self, moves: list[str], *, live_revision: int, view_revision: int) -> None:
        self._live_revision = live_revision
        self._view_revision = view_revision
        self.clear()
        for index, text in enumerate(moves, start=1):
            item = QListWidgetItem(text)
            item.setData(256, index)
            self.addItem(item)
            if index == view_revision:
                item.setSelected(True)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        revision = item.data(256)
        if isinstance(revision, int):
            self.revision_selected.emit(revision)
