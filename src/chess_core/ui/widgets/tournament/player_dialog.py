"""Dialogs for the tournament manager page."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PlayerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, player=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Игрок")
        self.name_edit = QLineEdit()
        self.rating = QSpinBox()
        self.rating.setRange(0, 4000)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("GM, IM, FM…")
        self.federation_edit = QLineEdit()
        self.federation_edit.setPlaceholderText("RUS, FID…")
        self.team_edit = QLineEdit()
        form = QFormLayout()
        form.addRow("Имя", self.name_edit)
        form.addRow("Рейтинг", self.rating)
        form.addRow("Звание", self.title_edit)
        form.addRow("Федерация", self.federation_edit)
        form.addRow("Клуб", self.team_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if player is not None:
            self.set_player(player)

    def set_player(self, player) -> None:
        self.name_edit.setText(player.name)
        self.rating.setValue(player.rating)
        self.title_edit.setText(player.title)
        self.federation_edit.setText(player.federation)
        self.team_edit.setText(player.team or "")

    def values(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "rating": self.rating.value(),
            "title": self.title_edit.text().strip(),
            "federation": self.federation_edit.text().strip(),
            "team": self.team_edit.text().strip() or None,
        }


class GoogleSheetDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Google Таблица")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://docs.google.com/spreadsheets/d/... (опубликованная)")
        form = QFormLayout()
        form.addRow("Ссылка CSV", self.url_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def url(self) -> str:
        return self.url_edit.text().strip()


class TournamentPropertiesDialog(QDialog):
    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Свойства турнира")
        self.name_edit = QLineEdit(settings.name)
        self.site_edit = QLineEdit(settings.site)
        self.arbiter_edit = QLineEdit(settings.arbiter)
        self.time_edit = QLineEdit(settings.time_control)
        form = QFormLayout()
        form.addRow("Название", self.name_edit)
        form.addRow("Место", self.site_edit)
        form.addRow("Судья", self.arbiter_edit)
        form.addRow("Контроль", self.time_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {
            "name": self.name_edit.text().strip() or "Tournament",
            "site": self.site_edit.text().strip(),
            "arbiter": self.arbiter_edit.text().strip(),
            "time_control": self.time_edit.text().strip(),
        }
