"""Move list sidebar widget (presentation only)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem, QSizePolicy


class MoveListWidget(QListWidget):
    revision_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._live_revision = 0
        self._view_revision = 0
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(260)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.itemClicked.connect(self._on_item_clicked)

    def set_moves(
        self,
        moves: list[str],
        *,
        live_revision: int,
        view_revision: int,
        include_initial: bool = False,
        revision_ranges: list[tuple[int, int]] | None = None,
    ) -> None:
        self._live_revision = live_revision
        self._view_revision = view_revision
        self.clear()
        if include_initial:
            initial = QListWidgetItem("Начальная позиция")
            initial.setData(256, 0)
            self.addItem(initial)
            if view_revision == 0:
                initial.setSelected(True)
        for index, text in enumerate(moves, start=1):
            start_revision, end_revision = (
                revision_ranges[index - 1]
                if revision_ranges is not None
                else (index, index)
            )
            item = QListWidgetItem(text)
            item.setData(256, end_revision)
            item.setData(257, (start_revision, end_revision))
            self.addItem(item)
            if start_revision <= view_revision <= end_revision:
                item.setSelected(True)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        revision = item.data(256)
        if isinstance(revision, int):
            self.revision_selected.emit(revision)
