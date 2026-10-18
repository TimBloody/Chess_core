"""Mode selection widgets for the PyQt UI shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chess_core.modes.orchestrator import (
    BASE_LABELS,
    FAMILY_BASES,
    FAMILY_LABELS,
    FAMILY_ORDER,
    LAYERS,
    OVERLAY_ORDER,
    ModeSpec,
    compatible_layers,
    family_for_base,
    parse_spec,
    spec_display_name,
    toggle_layer,
)
from chess_core.ui.theme import tighten_wrapping_label


@dataclass
class UiSession:
    """Small mutable UI session shared by shell widgets."""

    mode_id: str | None = None


class ModePicker(QWidget):
    """Family → variant, then chess overlays; store composed id in ``UiSession``."""

    mode_changed = pyqtSignal(str)

    def __init__(
        self,
        mode_ids: Iterable[str],
        session: UiSession,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modePicker")
        self._session = session
        self._known_ids = set(mode_ids)
        self._updating = False
        self._checkboxes: dict[str, QCheckBox] = {}

        family_title = QLabel("Семейство")
        family_title.setObjectName("panelTitle")
        self._family_combo = QComboBox()
        self._family_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._family_combo.setMinimumContentsLength(8)

        variant_title = QLabel("Режим")
        variant_title.setObjectName("panelTitle")
        self._combo = QComboBox()
        self._combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._combo.setMinimumContentsLength(8)

        self._overlays_title = QLabel("Совместить")
        self._overlays_title.setObjectName("panelTitle")
        overlays = QWidget()
        overlays.setObjectName("modeOverlays")
        self._overlays_layout = QVBoxLayout(overlays)
        self._overlays_layout.setContentsMargins(0, 0, 0, 0)
        self._overlays_layout.setSpacing(4)
        for layer_id in OVERLAY_ORDER:
            box = QCheckBox(LAYERS[layer_id].label)
            box.setProperty("layer_id", layer_id)
            box.toggled.connect(self._on_layer_toggled)
            self._overlays_layout.addWidget(box)
            self._checkboxes[layer_id] = box
        scroll = QScrollArea()
        scroll.setObjectName("modeOverlayScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(overlays)
        scroll.setMaximumHeight(280)
        scroll.viewport().setAutoFillBackground(False)
        self._status = QLabel()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(family_title)
        layout.addWidget(self._family_combo)
        layout.addWidget(variant_title)
        layout.addWidget(self._combo)
        layout.addWidget(self._overlays_title)
        layout.addWidget(scroll)
        layout.addWidget(self._status)
        self.setLayout(layout)

        for family_id in FAMILY_ORDER:
            if not self._family_reachable(family_id):
                continue
            self._family_combo.addItem(FAMILY_LABELS.get(family_id, family_id), family_id)

        self._family_combo.currentIndexChanged.connect(self._on_family_changed)
        self._combo.currentIndexChanged.connect(self._on_base_changed)
        tighten_wrapping_label(self._status)
        self._select_initial_mode()

    @property
    def selected_mode_id(self) -> str | None:
        return self._session.mode_id

    def current_spec(self) -> ModeSpec:
        base = self._combo.currentData()
        if not base:
            return ModeSpec("chess")
        layers = frozenset(
            layer_id for layer_id, box in self._checkboxes.items() if box.isChecked()
        )
        return ModeSpec(str(base), layers)

    def _family_reachable(self, family_id: str) -> bool:
        return any(self._base_reachable(base) for base in FAMILY_BASES.get(family_id, ()))

    def _base_reachable(self, base: str) -> bool:
        if not self._known_ids:
            return True
        if base in self._known_ids:
            return True
        for mode_id in self._known_ids:
            try:
                if parse_spec(mode_id).base == base:
                    return True
            except ValueError:
                continue
        return False

    def _refill_variants(self, family_id: str, preferred_base: str | None = None) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        for base in FAMILY_BASES.get(family_id, ()):
            if not self._base_reachable(base):
                continue
            self._combo.addItem(BASE_LABELS.get(base, base), base)
        if preferred_base is not None:
            index = self._combo.findData(preferred_base)
            if index >= 0:
                self._combo.setCurrentIndex(index)
        elif self._combo.count() > 0:
            self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)

    def _select_initial_mode(self) -> None:
        if self._family_combo.count() == 0:
            self._family_combo.setEnabled(False)
            self._combo.setEnabled(False)
            self._status.setText("Нет зарегистрированных режимов")
            self._session.mode_id = None
            return
        spec = ModeSpec("chess")
        if self._session.mode_id:
            try:
                spec = parse_spec(self._session.mode_id)
            except ValueError:
                spec = ModeSpec("chess")
        self._apply_spec(spec, emit=False)

    def _on_family_changed(self, _index: int) -> None:
        if self._updating:
            return
        family_id = str(self._family_combo.currentData() or "chess")
        self._refill_variants(family_id)
        base = str(self._combo.currentData() or FAMILY_BASES[family_id][0])
        self._apply_spec(ModeSpec(base), emit=True)

    def _on_base_changed(self, _index: int) -> None:
        if self._updating:
            return
        spec = ModeSpec(str(self._combo.currentData() or "chess"))
        self._apply_spec(spec, emit=True)

    def _on_layer_toggled(self, _checked: bool) -> None:
        if self._updating:
            return
        sender = self.sender()
        if not isinstance(sender, QCheckBox):
            return
        layer_id = str(sender.property("layer_id") or "")
        spec = toggle_layer(self.current_spec(), layer_id, sender.isChecked())
        self._apply_spec(spec, emit=True)

    def _apply_spec(self, spec: ModeSpec, *, emit: bool) -> None:
        self._updating = True
        family_id = family_for_base(spec.base)
        family_index = self._family_combo.findData(family_id)
        if family_index >= 0:
            self._family_combo.setCurrentIndex(family_index)
        self._refill_variants(family_id, preferred_base=spec.base)
        allowed = compatible_layers(spec.base, spec.layers)
        any_overlay = False
        for layer_id, box in self._checkboxes.items():
            applies = spec.base in LAYERS[layer_id].applies_to
            box.setVisible(applies)
            if not applies:
                box.setChecked(False)
                continue
            any_overlay = True
            box.setChecked(layer_id in spec.layers)
            enabled = layer_id in spec.layers or layer_id in allowed
            box.setEnabled(enabled)
            if not enabled:
                box.setToolTip("Не сочетается с уже выбранными режимами")
            else:
                box.setToolTip("")
        self._overlays_title.setVisible(any_overlay)
        encoded = spec.encoded()
        self._session.mode_id = encoded
        self._status.setText(f"Выбран: {spec_display_name(spec)}")
        self._updating = False
        if emit:
            self.mode_changed.emit(encoded)
