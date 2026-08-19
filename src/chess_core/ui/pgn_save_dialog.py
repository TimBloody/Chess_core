"""Metadata dialog for saving a game or analysis as PGN."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from chess_core.infra.pgn_storage import PgnMetadata


class PgnSaveDialog(QDialog):
    def __init__(
        self,
        defaults: PgnMetadata,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сохранить PGN для ChessBase")
        self.setMinimumWidth(440)

        self.event = QLineEdit(defaults.event)
        self.site = QLineEdit(defaults.site)
        self.played_on = QLineEdit(defaults.played_on)
        self.round = QLineEdit(defaults.round)
        self.white = QLineEdit(defaults.white)
        self.black = QLineEdit(defaults.black)
        self.result = QComboBox()
        self.result.addItems(("*", "1-0", "0-1", "1/2-1/2"))
        self.result.setCurrentText(defaults.result)
        self.white_elo = QLineEdit(defaults.white_elo)
        self.black_elo = QLineEdit(defaults.black_elo)
        self.eco = QLineEdit(defaults.eco)
        self.opening = QLineEdit(defaults.opening)
        self.variation = QLineEdit(defaults.variation)
        self.annotator = QLineEdit(defaults.annotator)
        self.filename = QLineEdit(defaults.suggested_filename())

        form = QFormLayout()
        form.addRow("Турнир / анализ:", self.event)
        form.addRow("Место:", self.site)
        form.addRow("Дата (ГГГГ.ММ.ДД):", self.played_on)
        form.addRow("Тур:", self.round)
        form.addRow("Белые:", self.white)
        form.addRow("Чёрные:", self.black)
        form.addRow("Результат:", self.result)
        form.addRow("Рейтинг белых:", self.white_elo)
        form.addRow("Рейтинг чёрных:", self.black_elo)
        form.addRow("ECO:", self.eco)
        form.addRow("Дебют:", self.opening)
        form.addRow("Вариант:", self.variation)
        form.addRow("Автор анализа:", self.annotator)
        form.addRow("Имя файла:", self.filename)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def metadata(self) -> PgnMetadata:
        return PgnMetadata(
            event=self.event.text().strip(),
            site=self.site.text().strip(),
            played_on=self.played_on.text().strip(),
            round=self.round.text().strip(),
            white=self.white.text().strip(),
            black=self.black.text().strip(),
            result=self.result.currentText(),
            white_elo=self.white_elo.text().strip(),
            black_elo=self.black_elo.text().strip(),
            eco=self.eco.text().strip(),
            opening=self.opening.text().strip(),
            variation=self.variation.text().strip(),
            annotator=self.annotator.text().strip(),
        )

    def requested_filename(self) -> str:
        return self.filename.text().strip()
