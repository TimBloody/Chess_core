"""Tournament pairing page. Displays application-layer draws, no game rules."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.tournament import (
    PairingSystem,
    TournamentService,
    parse_player_list,
)

_SYSTEM_LABELS = (
    (PairingSystem.ROUND_ROBIN, "Круговая (Бергер)"),
    (PairingSystem.SWISS, "Швейцарская"),
    (PairingSystem.KNOCKOUT, "Олимпийская"),
    (PairingSystem.SCHEVENINGEN, "Шевенинген"),
    (PairingSystem.COLOR_DRAW, "Жеребьёвка цвета"),
)


class TournamentWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service: TournamentService | None = None
        self.players_edit = QPlainTextEdit()
        self.players_edit.setPlaceholderText(
            "По одному игроку на строку: Имя|рейтинг|команда\n"
            "Команда нужна только для шевенингенской системы."
        )
        self.system = QComboBox()
        for system, label in _SYSTEM_LABELS:
            self.system.addItem(label, system)
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 32)
        self.rounds.setValue(5)
        self.seed = QSpinBox()
        self.seed.setRange(0, 1_000_000)
        self.seed.setValue(1)
        self.status = QLabel("Введите список игроков и нажмите «Следующий тур».")
        self.generate = QPushButton("Следующий тур")
        self.reset = QPushButton("Сброс")
        self.pairings = QTableWidget(0, 6)
        self.pairings.setHorizontalHeaderLabels(
            ("Тур", "Доска", "Белые", "Чёрные", "Результат", "")
        )
        self.standings = QTableWidget(0, 6)
        self.standings.setHorizontalHeaderLabels(
            ("Место", "Игрок", "Очки", "Партии", "+/=/−", "Бухгольц")
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Жеребьёвка"))
        layout.addWidget(self.players_edit, 1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Система"))
        controls.addWidget(self.system)
        controls.addWidget(QLabel("Туры (швейцарка)"))
        controls.addWidget(self.rounds)
        controls.addWidget(QLabel("Seed"))
        controls.addWidget(self.seed)
        controls.addWidget(self.generate)
        controls.addWidget(self.reset)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("Пары"))
        layout.addWidget(self.pairings, 2)
        layout.addWidget(QLabel("Таблица"))
        layout.addWidget(self.standings, 1)

        self.generate.clicked.connect(self._next_round)
        self.reset.clicked.connect(self._reset)
        self.system.currentIndexChanged.connect(self._reset)

    def _reset(self, *_args) -> None:
        self._service = None
        self.pairings.setRowCount(0)
        self.standings.setRowCount(0)
        self.status.setText("Введите список игроков и нажмите «Следующий тур».")

    def _next_round(self) -> None:
        try:
            if self._service is None:
                players = parse_player_list(self.players_edit.toPlainText())
                system = self.system.currentData()
                self._service = TournamentService(
                    system,
                    players,
                    swiss_rounds=self.rounds.value(),
                    seed=self.seed.value(),
                )
            self._service.generate_next_round()
            self.status.setText(f"Сгенерирован тур {self._service.current_round}.")
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))
            if self._service is not None and not self._service.pairings:
                self._service = None
            return
        self._refresh()

    def _refresh(self) -> None:
        if self._service is None:
            return
        names = {player.player_id: player.name for player in self._service.players}
        pairings = self._service.pairings
        self.pairings.setRowCount(len(pairings))
        for row, pairing in enumerate(pairings):
            self.pairings.setItem(row, 0, QTableWidgetItem(str(pairing.round_index)))
            self.pairings.setItem(row, 1, QTableWidgetItem(str(pairing.board)))
            self.pairings.setItem(
                row, 2, QTableWidgetItem(names.get(pairing.white_id or "", "BYE"))
            )
            self.pairings.setItem(
                row, 3, QTableWidgetItem(names.get(pairing.black_id or "", "BYE"))
            )
            self.pairings.setItem(row, 4, QTableWidgetItem(pairing.result or "—"))
            buttons = QWidget()
            row_layout = QHBoxLayout(buttons)
            row_layout.setContentsMargins(0, 0, 0, 0)
            if pairing.is_bye:
                row_layout.addWidget(QLabel("bye"))
            else:
                for result, label in (("1-0", "1-0"), ("1/2-1/2", "½"), ("0-1", "0-1")):
                    button = QPushButton(label)
                    button.clicked.connect(
                        self._make_result_handler(pairing.round_index, pairing.board, result)
                    )
                    row_layout.addWidget(button)
            self.pairings.setCellWidget(row, 5, buttons)

        table = self._service.standings()
        self.standings.setRowCount(len(table))
        for row, standing in enumerate(table):
            self.standings.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.standings.setItem(row, 1, QTableWidgetItem(standing.player.name))
            self.standings.setItem(row, 2, QTableWidgetItem(str(standing.points)))
            self.standings.setItem(row, 3, QTableWidgetItem(str(standing.games)))
            self.standings.setItem(
                row,
                4,
                QTableWidgetItem(f"{standing.wins}/{standing.draws}/{standing.losses}"),
            )
            self.standings.setItem(row, 5, QTableWidgetItem(str(standing.buchholz)))

    def _make_result_handler(self, round_index: int, board: int, result: str):
        def _set() -> None:
            if self._service is None:
                return
            try:
                self._service.set_result(round_index, board, result)
                self.status.setText(f"Тур {round_index}, доска {board}: {result}")
                self._refresh()
            except (ValueError, KeyError) as exc:
                self.status.setText(str(exc))

        return _set
