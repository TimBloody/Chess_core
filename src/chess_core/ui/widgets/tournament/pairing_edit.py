"""Manual pairing editor with a required reason field."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.tournament.models import Pairing, Player


class PairingEditDialog(QDialog):
    def __init__(
        self,
        players: tuple[Player, ...],
        pairings: tuple[Pairing, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Изменить пары")
        self._players = players
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Причина изменения (обязательно)")
        self.table = QTableWidget(len(pairings), 3)
        self.table.setHorizontalHeaderLabels(("Доска", "Белые", "Чёрные"))
        for row, pairing in enumerate(pairings):
            self.table.setItem(row, 0, QTableWidgetItem(str(pairing.board)))
            self.table.setCellWidget(row, 1, self._player_combo(pairing.white_id))
            self.table.setCellWidget(row, 2, self._player_combo(pairing.black_id))
        swap = QPushButton("Поменять цвета на выбранной доске")
        swap.clicked.connect(self._swap_selected)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Опоздавший или севший не за тот стол: поправьте пару и укажите причину."))
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(swap)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.reason_edit)
        layout.addWidget(buttons)

    def reason(self) -> str:
        return self.reason_edit.text().strip()

    def pairings(self, round_index: int) -> list[Pairing]:
        result: list[Pairing] = []
        for row in range(self.table.rowCount()):
            board_item = self.table.item(row, 0)
            board = int(board_item.text()) if board_item is not None else row + 1
            white = self._combo_id(self.table.cellWidget(row, 1))
            black = self._combo_id(self.table.cellWidget(row, 2))
            result.append(Pairing(round_index, board, white, black, "bye" if white is None or black is None else None))
        return result

    def _player_combo(self, selected: str | None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("BYE", None)
        for player in self._players:
            combo.addItem(f"{player.start_number}. {player.name}", player.player_id)
        index = combo.findData(selected)
        combo.setCurrentIndex(max(0, index))
        return combo

    def _combo_id(self, widget: QWidget | None) -> str | None:
        if not isinstance(widget, QComboBox):
            return None
        value = widget.currentData()
        return str(value) if value else None

    def _swap_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        left = self.table.cellWidget(row, 1)
        right = self.table.cellWidget(row, 2)
        if not isinstance(left, QComboBox) or not isinstance(right, QComboBox):
            return
        left_index, right_index = left.currentIndex(), right.currentIndex()
        left.setCurrentIndex(right_index)
        right.setCurrentIndex(left_index)
