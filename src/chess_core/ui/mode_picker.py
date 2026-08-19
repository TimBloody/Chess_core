"""Mode selection widgets for the PyQt UI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from chess_core.modes.variant_composition import (
    CANONICAL_MODIFIER_ORDER,
    CHESS_FAMILY_MODE_IDS,
    DUCK,
    THREE_CHECK,
    TWO_MOVE,
    canonical_modifier_ids,
    parse_modifier_ids_from_mode_id,
    resolve_chess_mode_id,
)
from chess_core.ui.assets_loader import SHOGI_PIECE_SETS, shogi_piece_set
from chess_core.ui.theme import mode_display_name


@dataclass
class UiSession:
    """Small mutable UI session shared by shell widgets."""

    mode_id: str | None = None


_MODIFIER_LABELS: dict[str, str] = {
    "chess960": "Chess960",
    "cylindrical": "Цилиндр",
    "crazyhouse": "Crazyhouse",
    "duck": "Утка",
    "two_move": "Двухходовки",
    "fairytale": "Fairytale",
    "three_check": "Три шаха",
    "king_of_the_hill": "Царь горы",
}


class ModePicker(QWidget):
    """Pick a registered game mode and store it in ``UiSession``."""

    mode_changed = pyqtSignal(str)
    piece_set_changed = pyqtSignal(str)

    def __init__(
        self,
        mode_ids: Iterable[str],
        session: UiSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._mode_ids = list(mode_ids)
        self._syncing = False

        title = QLabel("Режим")
        self._combo = QComboBox()
        self._status = QLabel()
        modifier_title = QLabel("Модификаторы")
        self._modifier_title = modifier_title
        self._modifier_boxes: dict[str, QCheckBox] = {}
        modifier_layout = QVBoxLayout()
        modifier_layout.setContentsMargins(0, 0, 0, 0)
        for modifier_id in CANONICAL_MODIFIER_ORDER:
            checkbox = QCheckBox(_MODIFIER_LABELS[modifier_id])
            checkbox.setProperty("modifier_id", modifier_id)
            checkbox.toggled.connect(self._on_modifier_toggled)
            self._modifier_boxes[modifier_id] = checkbox
            modifier_layout.addWidget(checkbox)
        self._modifier_panel = QWidget()
        self._modifier_panel.setLayout(modifier_layout)
        piece_title = QLabel("Фигуры сёги")
        self._piece_set = QComboBox()

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self._combo)
        layout.addWidget(self._status)
        layout.addWidget(modifier_title)
        layout.addWidget(self._modifier_panel)
        layout.addSpacing(8)
        layout.addWidget(piece_title)
        layout.addWidget(self._piece_set)
        self.setLayout(layout)

        for mode_id in self._mode_ids:
            self._combo.addItem(mode_display_name(mode_id), mode_id)
        current_set = shogi_piece_set()
        for key, label in SHOGI_PIECE_SETS.items():
            self._piece_set.addItem(label, key)
            if key == current_set:
                self._piece_set.setCurrentIndex(self._piece_set.count() - 1)

        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        self._piece_set.currentIndexChanged.connect(self._on_piece_set_changed)
        self._select_initial_mode()
        if self._session.mode_id is not None:
            self._update_modifier_panel_visibility(self._session.mode_id)

    @property
    def selected_mode_id(self) -> str | None:
        return self._session.mode_id

    def _select_initial_mode(self) -> None:
        if not self._mode_ids:
            self._combo.setEnabled(False)
            self._status.setText("Нет зарегистрированных режимов")
            self._session.mode_id = None
            return

        initial_index = 0
        if self._session.mode_id in self._mode_ids:
            initial_index = self._mode_ids.index(self._session.mode_id)
        elif self._session.mode_id is not None:
            composed = resolve_chess_mode_id(
                parse_modifier_ids_from_mode_id(self._session.mode_id)
            )
            if composed in self._mode_ids:
                initial_index = self._mode_ids.index(composed)

        self._combo.setCurrentIndex(initial_index)
        self._set_session_mode(initial_index)

    def _on_mode_changed(self, index: int) -> None:
        mode_id = self._combo.itemData(index)
        if mode_id is None:
            return
        mode_id = str(mode_id)
        if mode_id in CHESS_FAMILY_MODE_IDS:
            self._syncing = True
            self._sync_modifier_checkboxes(mode_id)
            self._update_modifier_conflicts()
            self._syncing = False
            resolved = self._resolve_mode_id_from_checkboxes()
        else:
            self._syncing = True
            self._sync_modifier_checkboxes("chess")
            self._update_modifier_conflicts()
            self._syncing = False
            resolved = mode_id
        self._apply_mode_id(resolved, emit=True)

    def _on_modifier_toggled(self, _checked: bool) -> None:
        if self._syncing:
            return
        combo_mode = str(self._combo.currentData())
        if combo_mode not in CHESS_FAMILY_MODE_IDS:
            return
        self._update_modifier_conflicts()
        resolved = self._resolve_mode_id_from_checkboxes()
        self._apply_mode_id(resolved, emit=True)

    def _set_session_mode(self, index: int) -> str | None:
        mode_id = self._combo.itemData(index)
        if mode_id is None:
            return None

        mode_id = str(mode_id)
        if mode_id in CHESS_FAMILY_MODE_IDS:
            self._syncing = True
            self._sync_modifier_checkboxes(mode_id)
            self._update_modifier_conflicts()
            self._syncing = False
            resolved = self._resolve_mode_id_from_checkboxes()
        else:
            self._syncing = True
            self._sync_modifier_checkboxes("chess")
            self._update_modifier_conflicts()
            self._syncing = False
            resolved = mode_id
        return self._apply_mode_id(resolved, emit=False)

    def _apply_mode_id(self, mode_id: str, *, emit: bool) -> str:
        self._session.mode_id = mode_id
        self._status.setText(f"Выбран: {mode_display_name(mode_id)}")
        self._update_modifier_panel_visibility(mode_id)
        if emit:
            self.mode_changed.emit(mode_id)
        return mode_id

    def _update_modifier_panel_visibility(self, mode_id: str) -> None:
        combo_mode = str(self._combo.currentData())
        show_modifiers = combo_mode in CHESS_FAMILY_MODE_IDS
        self._modifier_panel.setVisible(show_modifiers)
        self._modifier_title.setVisible(show_modifiers)

    def _sync_modifier_checkboxes(self, mode_id: str) -> None:
        modifiers = parse_modifier_ids_from_mode_id(mode_id)
        modifier_set = frozenset(modifiers)
        for modifier_id, checkbox in self._modifier_boxes.items():
            checkbox.setChecked(modifier_id in modifier_set)

    def _resolve_mode_id_from_checkboxes(self) -> str:
        selected = tuple(
            modifier_id
            for modifier_id in CANONICAL_MODIFIER_ORDER
            if self._modifier_boxes[modifier_id].isChecked()
        )
        return resolve_chess_mode_id(canonical_modifier_ids(selected))

    def _update_modifier_conflicts(self) -> None:
        duck_checked = self._modifier_boxes[DUCK.id].isChecked()
        two_move_box = self._modifier_boxes[TWO_MOVE.id]
        three_check_box = self._modifier_boxes[THREE_CHECK.id]
        two_move_box.setEnabled(not duck_checked)
        three_check_box.setEnabled(not duck_checked)
        if duck_checked:
            two_move_box.setChecked(False)
            three_check_box.setChecked(False)
        duck_box = self._modifier_boxes[DUCK.id]
        duck_box.setEnabled(not two_move_box.isChecked() and not three_check_box.isChecked())

    def _on_piece_set_changed(self, index: int) -> None:
        name = self._piece_set.itemData(index)
        if name is not None:
            self.piece_set_changed.emit(str(name))
