"""Mode selection widgets for the PyQt UI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from chess_core.modes.checkers import CHECKERS_MODIFIERS
from chess_core.modes.corners import CORNER_LAYOUTS, corners_mode_id
from chess_core.modes.gobblet import GOBBLET_RELOCATE, gobblet_mode_id
from chess_core.modes.gobblet_rules import GobbletOptions
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

CHECKERS_MODIFIER_LABELS = {
    "mandatory_capture": "Обязательное взятие",
    "backward_capture": "Простая бьёт назад",
    "flying_king": "Дальнобойная дамка",
}

CORNER_LAYOUT_LABELS = {
    "3x3": "Мини 3×3",
    "3x4": "Прямоугольник 3×4",
    "1234": "Треугольник 1–2–3–4",
}

GOBBLET_RELOCATE_LABEL = "Перемещать фигуры на доске"


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

        self._checkers_panel = QWidget()
        self._checkers_panel.hide()
        checkers_layout = QVBoxLayout(self._checkers_panel)
        checkers_layout.setContentsMargins(0, 8, 0, 0)
        self._checker_boxes: dict[str, QCheckBox] = {}
        for modifier in CHECKERS_MODIFIERS:
            box = QCheckBox(CHECKERS_MODIFIER_LABELS[modifier])
            box.setChecked(True)
            box.toggled.connect(self._on_checkers_modifier_changed)
            checkers_layout.addWidget(box)
            self._checker_boxes[modifier] = box

        self._corners_panel = QWidget()
        self._corners_panel.hide()
        corners_layout = QVBoxLayout(self._corners_panel)
        corners_layout.setContentsMargins(0, 8, 0, 0)
        corners_layout.addWidget(QLabel("Стартовая позиция"))
        self._corners_group = QButtonGroup(self)
        self._corners_group.setExclusive(True)
        self._corner_boxes: dict[str, QCheckBox] = {}
        for layout_id in CORNER_LAYOUTS:
            box = QCheckBox(CORNER_LAYOUT_LABELS[layout_id])
            box.setChecked(layout_id == "3x4")
            self._corners_group.addButton(box)
            box.toggled.connect(self._on_corners_layout_changed)
            corners_layout.addWidget(box)
            self._corner_boxes[layout_id] = box

        self._gobblet_panel = QWidget()
        self._gobblet_panel.hide()
        gobblet_layout = QVBoxLayout(self._gobblet_panel)
        gobblet_layout.setContentsMargins(0, 8, 0, 0)
        self._gobblet_relocate = QCheckBox(GOBBLET_RELOCATE_LABEL)
        self._gobblet_relocate.toggled.connect(self._on_gobblet_relocate_changed)
        gobblet_layout.addWidget(self._gobblet_relocate)

        piece_title = QLabel("Фигуры сёги")
        self._piece_set = QComboBox()

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self._combo)
        layout.addWidget(self._status)
        layout.addWidget(modifier_title)
        layout.addWidget(self._modifier_panel)
        layout.addWidget(self._checkers_panel)
        layout.addWidget(self._corners_panel)
        layout.addWidget(self._gobblet_panel)
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
            self._modifier_panel.setVisible(False)
            self._modifier_title.setVisible(False)
            self._checkers_panel.setVisible(False)
            self._corners_panel.setVisible(False)
            self._gobblet_panel.setVisible(False)
            return

        initial_index = 0
        session_id = self._session.mode_id
        base_id = _base_mode_id(session_id)
        if session_id in self._mode_ids:
            initial_index = self._mode_ids.index(session_id)
        elif base_id in self._mode_ids:
            initial_index = self._mode_ids.index(base_id)
        elif session_id is not None:
            composed = resolve_chess_mode_id(
                parse_modifier_ids_from_mode_id(session_id)
            )
            if composed in self._mode_ids:
                initial_index = self._mode_ids.index(composed)

        self._apply_checkers_boxes(session_id)
        self._apply_corners_boxes(session_id)
        self._apply_gobblet_box(session_id)
        self._combo.setCurrentIndex(initial_index)
        self._set_session_mode(initial_index)

    def _on_mode_changed(self, index: int) -> None:
        mode_id = self._combo.itemData(index)
        if mode_id is None:
            return
        previous = _base_mode_id(self._session.mode_id)
        self._apply_mode_id(
            self._resolve_combo_mode(str(mode_id), resetting=previous != str(mode_id)),
            emit=True,
        )

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
        return self._apply_mode_id(
            self._resolve_combo_mode(str(mode_id), resetting=False),
            emit=False,
        )

    def _resolve_combo_mode(self, base_id: str, *, resetting: bool) -> str:
        if base_id in CHESS_FAMILY_MODE_IDS:
            self._syncing = True
            self._sync_modifier_checkboxes(base_id)
            self._update_modifier_conflicts()
            self._syncing = False
            return self._resolve_mode_id_from_checkboxes()
        self._syncing = True
        self._sync_modifier_checkboxes("chess")
        self._update_modifier_conflicts()
        self._syncing = False
        if base_id == "checkers":
            if resetting:
                self._apply_checkers_boxes("checkers")
            return self._composed_checkers_id()
        if base_id == "corners":
            if resetting:
                self._apply_corners_boxes("corners")
            return self._composed_corners_id()
        if base_id == "gobblet":
            if resetting:
                self._apply_gobblet_box("gobblet")
            return self._composed_gobblet_id()
        return base_id

    def _apply_mode_id(self, mode_id: str, *, emit: bool) -> str:
        self._session.mode_id = mode_id
        self._status.setText(f"Выбран: {mode_display_name(mode_id)}")
        self._update_modifier_panel_visibility(mode_id)
        if emit:
            self.mode_changed.emit(mode_id)
        return mode_id

    def _update_modifier_panel_visibility(self, mode_id: str) -> None:
        combo_mode = str(self._combo.currentData() or "")
        base = _base_mode_id(mode_id) or combo_mode
        show_modifiers = combo_mode in CHESS_FAMILY_MODE_IDS
        self._modifier_panel.setVisible(show_modifiers)
        self._modifier_title.setVisible(show_modifiers)
        self._checkers_panel.setVisible(base == "checkers")
        self._corners_panel.setVisible(base == "corners")
        self._gobblet_panel.setVisible(base == "gobblet")

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

    def _on_checkers_modifier_changed(self) -> None:
        if self._syncing:
            return
        if str(self._combo.currentData()) != "checkers":
            return
        self._apply_mode_id(self._composed_checkers_id(), emit=True)

    def _on_corners_layout_changed(self) -> None:
        if self._syncing:
            return
        if str(self._combo.currentData()) != "corners":
            return
        self._apply_mode_id(self._composed_corners_id(), emit=True)

    def _on_gobblet_relocate_changed(self) -> None:
        if self._syncing:
            return
        if str(self._combo.currentData()) != "gobblet":
            return
        self._apply_mode_id(self._composed_gobblet_id(), emit=True)

    def _composed_checkers_id(self) -> str:
        enabled = [
            modifier
            for modifier in CHECKERS_MODIFIERS
            if self._checker_boxes[modifier].isChecked()
        ]
        if not enabled:
            return "checkers+none"
        if len(enabled) == len(CHECKERS_MODIFIERS):
            return "checkers"
        return "+".join(("checkers", *enabled))

    def _composed_corners_id(self) -> str:
        return corners_mode_id(self._selected_corners_layout())

    def _selected_corners_layout(self) -> str:
        for layout_id, box in self._corner_boxes.items():
            if box.isChecked():
                return layout_id
        return "3x4"

    def _apply_checkers_boxes(self, mode_id: str | None) -> None:
        self._syncing = True
        try:
            if mode_id is None or _base_mode_id(mode_id) != "checkers":
                for box in self._checker_boxes.values():
                    box.setChecked(True)
                return
            parts = [part for part in mode_id.split("+") if part][1:]
            if not parts:
                enabled = set(CHECKERS_MODIFIERS)
            elif parts == ["none"]:
                enabled = set()
            else:
                enabled = set(parts)
            for modifier, box in self._checker_boxes.items():
                box.setChecked(modifier in enabled)
        finally:
            self._syncing = False

    def _apply_corners_boxes(self, mode_id: str | None) -> None:
        self._syncing = True
        try:
            layout = "3x4"
            if mode_id is not None and _base_mode_id(mode_id) == "corners":
                parts = [part for part in mode_id.split("+") if part]
                if len(parts) == 2 and parts[1] in CORNER_LAYOUTS:
                    layout = parts[1]
            for layout_id, box in self._corner_boxes.items():
                box.setChecked(layout_id == layout)
        finally:
            self._syncing = False

    def _composed_gobblet_id(self) -> str:
        return gobblet_mode_id(
            GobbletOptions(allow_board_moves=self._gobblet_relocate.isChecked())
        )

    def _apply_gobblet_box(self, mode_id: str | None) -> None:
        self._syncing = True
        try:
            relocate = False
            if mode_id is not None and _base_mode_id(mode_id) == "gobblet":
                parts = [part for part in mode_id.split("+") if part]
                relocate = GOBBLET_RELOCATE in parts[1:]
            self._gobblet_relocate.setChecked(relocate)
        finally:
            self._syncing = False


def _base_mode_id(mode_id: str | None) -> str | None:
    if not mode_id:
        return None
    return mode_id.split("+", 1)[0]
