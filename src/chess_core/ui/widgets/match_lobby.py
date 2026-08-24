"""Lobby seat grid for 2- and 4-player matches."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from chess_core.app.seats import SPECTATOR, seats_for_match_kind
from chess_core.infra.network_messages import LobbyState


class MatchLobbyWidget(QWidget):
    seat_chosen = pyqtSignal(str)
    start_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = "single"
        self._session_id = ""
        self._is_host = False
        self._buttons: dict[str, QPushButton] = {}
        self._status = QLabel("Подключение…")
        self._start = QPushButton("Начать партию")
        self._start.clicked.connect(self.start_requested.emit)
        self._spectator = QPushButton("Зритель")
        self._spectator.clicked.connect(lambda: self.seat_chosen.emit(SPECTATOR))
        self._grid = QGridLayout()
        layout = QVBoxLayout(self)
        layout.addWidget(self._status)
        layout.addLayout(self._grid)
        layout.addWidget(self._spectator)
        layout.addWidget(self._start)

    def set_context(self, *, match_kind: str, session_id: str, is_host: bool) -> None:
        self._kind = match_kind
        self._session_id = session_id
        self._is_host = is_host
        self._rebuild()

    def apply_lobby(self, lobby: LobbyState) -> None:
        occupied = {occupant.seat: occupant for occupant in lobby.occupants}
        for seat_id, button in self._buttons.items():
            occupant = occupied.get(seat_id)
            if occupant is None:
                button.setText(self._label(seat_id) + " — свободно")
                button.setEnabled(True)
            elif occupant.session_id == self._session_id:
                button.setText(self._label(seat_id) + " — вы")
                button.setEnabled(True)
            else:
                button.setText(self._label(seat_id) + " — занято")
                button.setEnabled(False)
        filled = all(seat in occupied for seat in lobby.required_seats)
        self._start.setVisible(self._is_host)
        self._start.setEnabled(self._is_host and filled and lobby.phase.name == "LOBBY")
        phase = {
            "LOBBY": "Лобби: выберите место. Чтобы пересесть, сначала станьте зрителем.",
            "PLAYING": "Партия идёт.",
            "ENDED": "Партия окончена.",
        }.get(lobby.phase.name, lobby.phase.name)
        self._status.setText(phase)

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()
        specs = seats_for_match_kind(self._kind)
        for index, spec in enumerate(specs):
            button = QPushButton(spec.label)
            button.clicked.connect(lambda _=False, seat=spec.seat_id: self.seat_chosen.emit(seat))
            self._buttons[spec.seat_id] = button
            self._grid.addWidget(button, index // 2, index % 2)

    def _label(self, seat_id: str) -> str:
        for spec in seats_for_match_kind(self._kind):
            if spec.seat_id == seat_id:
                return spec.label
        return seat_id
