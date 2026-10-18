"""Result combo that keeps keyboard focus on the pairing list."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QWheelEvent
from PyQt6.QtWidgets import QComboBox

from chess_core.app.tournament.models import (
    RESULT_BLACK,
    RESULT_DRAW,
    RESULT_FORFEIT_BLACK,
    RESULT_FORFEIT_WHITE,
    RESULT_WHITE,
)

_RESULT_KEYS = {
    Qt.Key.Key_1: RESULT_WHITE,
    Qt.Key.Key_2: RESULT_DRAW,
    Qt.Key.Key_5: RESULT_DRAW,
    Qt.Key.Key_Equal: RESULT_DRAW,
    Qt.Key.Key_0: RESULT_BLACK,
    Qt.Key.Key_Plus: RESULT_FORFEIT_WHITE,
    Qt.Key.Key_Minus: RESULT_FORFEIT_BLACK,
}


class ResultCombo(QComboBox):
    """Up/Down move between boards; Left/Right and 1/2/0 set the result."""

    navigate = pyqtSignal(int)
    advance = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.view() is not None and self.view().isVisible():
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Up:
            self.navigate.emit(-1)
            event.accept()
            return
        if key in {Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.navigate.emit(1)
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            self._cycle(-1)
            event.accept()
            return
        if key in {Qt.Key.Key_Right, Qt.Key.Key_Space}:
            self._cycle(1)
            event.accept()
            return
        result = _RESULT_KEYS.get(key)
        if result is not None:
            self._select_result(result)
            self.advance.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def _cycle(self, delta: int) -> None:
        count = self.count()
        if count <= 1:
            return
        index = self.currentIndex()
        for _ in range(count):
            index = (index + delta) % count
            if self.itemData(index):
                self.setCurrentIndex(index)
                return

    def _select_result(self, result: str) -> None:
        index = self.findData(result)
        if index >= 0:
            self.setCurrentIndex(index)
