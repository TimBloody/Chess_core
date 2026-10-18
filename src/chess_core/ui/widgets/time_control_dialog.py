"""Dialog for choosing a time control, including untimed play."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_core.core.time_control import TimeControlConfig, TimeControlKind

_KIND_LABELS: tuple[tuple[TimeControlKind, str], ...] = (
    (TimeControlKind.NONE, "Без времени"),
    (TimeControlKind.FISCHER, "Фишер"),
    (TimeControlKind.BRONSTEIN, "Бронштейн"),
    (TimeControlKind.BYOYOMI, "Байоми"),
)


class TimeControlDialog(QDialog):
    """Format, main minutes, and extra seconds (increment / delay / byoyomi)."""

    def __init__(self, initial: TimeControlConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Контроль времени")
        self.setModal(True)
        self.kind_combo = QComboBox()
        for kind, label in _KIND_LABELS:
            self.kind_combo.addItem(label, kind)
        self.main_minutes = QSpinBox()
        self.main_minutes.setRange(0, 180)
        self.main_minutes.setSuffix(" мин")
        self.extra_seconds = QSpinBox()
        self.extra_seconds.setRange(0, 180)
        self.extra_seconds.setSuffix(" сек")
        self.kind_combo.currentIndexChanged.connect(self._sync_fields)
        self._load(initial)

        form = QFormLayout()
        form.addRow("Формат", self.kind_combo)
        form.addRow("Основное время", self.main_minutes)
        form.addRow("Добавочное время", self.extra_seconds)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_button is not None:
            ok_button.setText("ОК")
        if cancel_button is not None:
            cancel_button.setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def config(self) -> TimeControlConfig:
        kind = self.kind_combo.currentData()
        if kind is TimeControlKind.NONE:
            return TimeControlConfig.none()
        if not isinstance(kind, TimeControlKind):
            kind = TimeControlKind.FISCHER
        return TimeControlConfig.from_parts(
            kind,
            main_minutes=self.main_minutes.value(),
            extra_seconds=self.extra_seconds.value(),
        )

    def _load(self, initial: TimeControlConfig) -> None:
        kind = initial.kind
        if kind is TimeControlKind.SIMPLE:
            kind = TimeControlKind.FISCHER
        index = self.kind_combo.findData(kind)
        self.kind_combo.setCurrentIndex(max(0, index))
        self.main_minutes.setValue(initial.main_minutes)
        self.extra_seconds.setValue(initial.extra_seconds)
        self._sync_fields()

    def _sync_fields(self) -> None:
        timed = self.kind_combo.currentData() is not TimeControlKind.NONE
        self.main_minutes.setEnabled(timed)
        self.extra_seconds.setEnabled(timed)
