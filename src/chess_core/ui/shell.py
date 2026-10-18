"""Shared branch window: nav rail and lazily constructed pages."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from chess_core.ui.mode_picker import ModePicker, UiSession
from chess_core.ui.theme import FullscreenMainWindow, app_icon


@dataclass(frozen=True, slots=True)
class PageSpec:
    """One nav-rail page. ``factory`` runs on first visit."""

    title: str
    factory: Callable[[], QWidget]
    follows_mode: bool = False


class BranchWindow(FullscreenMainWindow):
    """One product branch: optional mode picker and lazy pages."""

    def __init__(
        self,
        title: str,
        pages: Sequence[PageSpec],
        *,
        mode_ids: Iterable[str] | None = None,
        session: UiSession | None = None,
        show_mode_picker: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session or UiSession()
        self.setWindowTitle(title)
        self.setWindowIcon(app_icon())
        self.resize(1100, 720)

        self._specs = list(pages)
        self._widgets: list[QWidget | None] = [None] * len(self._specs)
        self._buttons: list[QPushButton] = []

        root = QWidget()
        root.setObjectName("rootPane")
        root_layout = QHBoxLayout()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        rail = QWidget()
        rail.setObjectName("navRail")
        rail.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        rail.setMaximumWidth(240)
        sidebar = QVBoxLayout(rail)

        mode_ids = list(mode_ids or ())
        if show_mode_picker:
            if self.session.mode_id is None and mode_ids:
                self.session.mode_id = mode_ids[0]
            picker = ModePicker(mode_ids, self.session)
            picker.mode_changed.connect(self._on_mode_changed)
            sidebar.addWidget(picker)
            sidebar.addSpacing(12)
            self._picker = picker
        else:
            self._picker = None

        self._stack = QStackedWidget()
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for index, spec in enumerate(self._specs):
            button = QPushButton(spec.title)
            button.setCheckable(True)
            self._nav_group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, page_index=index: self.show_page(page_index)
            )
            sidebar.addWidget(button)
            self._buttons.append(button)
            if index == 0:
                button.setChecked(True)
        sidebar.addStretch()
        sidebar.addWidget(self.theme_button)
        self.fullscreen_button = QPushButton("Полный экран")
        self.fullscreen_button.setCheckable(True)
        self.fullscreen_button.setToolTip("F11 — полный экран, Esc — обычное окно")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        sidebar.addWidget(self.fullscreen_button)
        root_layout.addWidget(rail, 0)
        root_layout.addWidget(self._stack, 1)
        if self._specs:
            self.show_page(0)
        self._fit_to_screen()

    def show_page(self, index: int) -> None:
        if not 0 <= index < len(self._specs):
            return
        widget = self._ensure_page(index)
        self._stack.setCurrentWidget(widget)
        button = self._buttons[index]
        if not button.isChecked():
            button.setChecked(True)

    def page_widget(self, title: str) -> QWidget:
        for index, spec in enumerate(self._specs):
            if spec.title == title:
                return self._ensure_page(index)
        raise KeyError(f"unknown page: {title}")

    def show_page_title(self, title: str) -> QWidget:
        for index, spec in enumerate(self._specs):
            if spec.title == title:
                self.show_page(index)
                return self._ensure_page(index)
        raise KeyError(f"unknown page: {title}")

    def closeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        for widget in self._widgets:
            if widget is not None:
                widget.close()
        super().closeEvent(event)

    def changeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "fullscreen_button"):
            self.fullscreen_button.setChecked(self.isFullScreen())
        super().changeEvent(event)

    def _ensure_page(self, index: int) -> QWidget:
        existing = self._widgets[index]
        if existing is not None:
            return existing
        spec = self._specs[index]
        widget = spec.factory()
        if spec.follows_mode and self.session.mode_id is not None and hasattr(widget, "set_mode"):
            widget.set_mode(self.session.mode_id)
        self._stack.addWidget(widget)
        self._widgets[index] = widget
        return widget

    def _on_mode_changed(self, mode_id: str) -> None:
        for spec, widget in zip(self._specs, self._widgets, strict=True):
            if widget is None or not spec.follows_mode:
                continue
            setter = getattr(widget, "set_mode", None)
            if setter is not None:
                setter(mode_id)

    def _fit_to_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        width = min(self.width(), max(720, int(avail.width() * 0.92)))
        height = min(self.height(), max(540, int(avail.height() * 0.92)))
        self.resize(width, height)
