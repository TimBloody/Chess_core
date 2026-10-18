"""Elo modeling experiment UI."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.experiments.elo import RatedPlayer, round_robin
from chess_core.ui.theme import tighten_wrapping_label

_SEED_PLAYERS = (
    ("Алиса", 1840.0),
    ("Борис", 1760.0),
    ("Вера", 1620.0),
    ("Глеб", 1510.0),
    ("Дина", 1480.0),
    ("Егор", 1390.0),
)


class EloExperimentWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._players = [RatedPlayer(name, rating) for name, rating in _SEED_PLAYERS]
        self._games: list = []

        title = QLabel("Модель рейтинга Эло")
        title.setObjectName("panelTitle")
        hint = QLabel(
            "Круговой турнир с исходами, нарисованными из ожидаемого счёта Эло. "
            "Это модель системы, а не обсчёт реальных партий."
        )
        tighten_wrapping_label(hint)

        self.k_input = QSpinBox()
        self.k_input.setRange(1, 80)
        self.k_input.setValue(20)
        self.run_button = QPushButton("Сыграть круг")
        self.reset_button = QPushButton("Сброс")
        self.run_button.clicked.connect(self._run_round)
        self.reset_button.clicked.connect(self._reset)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("K"))
        controls.addWidget(self.k_input)
        controls.addWidget(self.run_button)
        controls.addWidget(self.reset_button)
        controls.addStretch()

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Игрок", "Рейтинг", "Партии", "Очки"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.log = QLabel("Ещё не сыграно ни одной партии.")
        tighten_wrapping_label(self.log)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(controls)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.log)
        self._refresh_table()

    def _run_round(self) -> None:
        self._players, games = round_robin(self._players, k=float(self.k_input.value()))
        self._games.extend(games)
        last = games[-1] if games else None
        if last is None:
            self.log.setText("Некого сводить.")
        else:
            self.log.setText(
                f"Круг: {len(games)} партий. Последняя: {last.white} — {last.black} {last.result} "
                f"(ожидание белых {last.expected_white:.2f})."
            )
        self._refresh_table()

    def _reset(self) -> None:
        self._players = [RatedPlayer(name, rating) for name, rating in _SEED_PLAYERS]
        self._games = []
        self.log.setText("Рейтинги сброшены.")
        self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._players))
        for row, player in enumerate(self._players):
            self.table.setItem(row, 0, QTableWidgetItem(player.name))
            self.table.setItem(row, 1, QTableWidgetItem(f"{player.rating:.1f}"))
            self.table.setItem(row, 2, QTableWidgetItem(str(player.games)))
            self.table.setItem(row, 3, QTableWidgetItem(f"{player.score:.1f}"))
