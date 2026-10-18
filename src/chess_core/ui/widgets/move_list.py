"""Move list sidebar widget (presentation only)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from chess_core.app.game_record import MoveLogLine

_USER_ROLE = int(Qt.ItemDataRole.UserRole)
_COL_NUMBER = 0
_COL_WHITE = 1
_COL_BLACK = 2


class MoveListWidget(QTableWidget):
    revision_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("moveList")
        self._live_revision = 0
        self._view_revision = 0
        self._lines: tuple[MoveLogLine, ...] = ()
        self.setColumnCount(3)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setSectionResizeMode(_COL_NUMBER, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(_COL_WHITE, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(_COL_BLACK, QHeaderView.ResizeMode.Stretch)
        self.cellClicked.connect(self._on_cell_clicked)

    def set_moves(
        self,
        moves: Sequence[MoveLogLine] | Sequence[str],
        *,
        live_revision: int,
        view_revision: int,
        item_revisions: Sequence[int] | None = None,
    ) -> None:
        self._live_revision = live_revision
        self._view_revision = view_revision
        self._lines = self._coerce_lines(moves, item_revisions)
        self.blockSignals(True)
        self.clearContents()
        self.setRowCount(len(self._lines))
        for row, line in enumerate(self._lines):
            self._set_number_cell(row, line)
            self._set_ply_cell(row, _COL_WHITE, line.white, line.white_revision)
            self._set_ply_cell(row, _COL_BLACK, line.black, line.black_revision)
        self._select_view_revision(view_revision)
        self.blockSignals(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            if self._step_ply(1):
                event.accept()
                return
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            if self._step_ply(-1):
                event.accept()
                return
        super().keyPressEvent(event)

    def _coerce_lines(
        self,
        moves: Sequence[MoveLogLine] | Sequence[str],
        item_revisions: Sequence[int] | None,
    ) -> tuple[MoveLogLine, ...]:
        if moves and isinstance(moves[0], MoveLogLine):
            return tuple(line for line in moves if isinstance(line, MoveLogLine))
        texts = [str(item) for item in moves]
        if item_revisions is not None and len(item_revisions) == len(texts):
            revisions = list(item_revisions)
        else:
            revisions = list(range(1, len(texts) + 1))
        return tuple(
            MoveLogLine(number=index, white=text, white_revision=revision)
            for index, (text, revision) in enumerate(zip(texts, revisions), start=1)
        )

    def _set_number_cell(self, row: int, line: MoveLogLine) -> None:
        item = QTableWidgetItem(f"{line.number}.")
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item.setData(_USER_ROLE, line.end_revision)
        self.setItem(row, _COL_NUMBER, item)

    def _set_ply_cell(self, row: int, column: int, text: str, revision: int | None) -> None:
        item = QTableWidgetItem(text)
        if revision is None:
            item.setFlags(Qt.ItemFlag.NoItemFlags)
        else:
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(_USER_ROLE, revision)
        self.setItem(row, column, item)

    def _select_view_revision(self, view_revision: int) -> None:
        self.clearSelection()
        if view_revision <= 0:
            return
        target = self._cell_for_revision(view_revision)
        if target is None:
            return
        row, column = target
        self.setCurrentCell(row, column)
        item = self.item(row, column)
        if item is not None:
            item.setSelected(True)
            self.scrollToItem(item)

    def _cell_for_revision(self, revision: int) -> tuple[int, int] | None:
        fallback: tuple[int, int] | None = None
        for row, line in enumerate(self._lines):
            if line.white_revision == revision:
                return (row, _COL_WHITE)
            if line.black_revision == revision:
                return (row, _COL_BLACK)
            if line.white_revision is not None and line.white_revision <= revision:
                fallback = (row, _COL_WHITE)
            if line.black_revision is not None and line.black_revision <= revision:
                fallback = (row, _COL_BLACK)
        return fallback

    def _ply_revisions(self) -> list[int]:
        plies: list[int] = []
        for line in self._lines:
            plies.extend(line.ply_revisions())
        return plies

    def _step_ply(self, delta: int) -> bool:
        plies = self._ply_revisions()
        if not plies:
            return False
        current = self._view_revision
        if current in plies:
            index = plies.index(current) + delta
        elif delta > 0:
            index = next((i for i, ply in enumerate(plies) if ply > current), len(plies) - 1)
        else:
            matches = [i for i, ply in enumerate(plies) if ply < current]
            index = matches[-1] if matches else 0
        index = max(0, min(index, len(plies) - 1))
        target = plies[index]
        if target == current:
            return True
        self.revision_selected.emit(target)
        return True

    def _on_cell_clicked(self, row: int, column: int) -> None:
        item = self.item(row, column)
        if item is None:
            return
        revision = item.data(_USER_ROLE)
        if isinstance(revision, int) and revision > 0:
            self.revision_selected.emit(revision)
