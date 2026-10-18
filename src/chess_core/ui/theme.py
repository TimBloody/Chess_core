"""Lightweight presentation theme for the desktop shell."""

from __future__ import annotations

import sys
from enum import Enum

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from chess_core.ui.assets_loader import AssetsLoader

THEME_SHORTCUT = "Ctrl+Shift+T"
_SETTINGS_ORG = "ChessCore"
_SETTINGS_APP = "desktop"
_SETTINGS_KEY = "ui/theme"


class ThemeKind(Enum):
    DARK = "dark"
    LIGHT = "light"

SHELL_STYLESHEET = """
QMainWindow, QWidget#rootPane, QStackedWidget, QDialog {
    background: #1e1e1e;
    color: #ece6da;
}
QDialog QPushButton {
    text-align: center;
    min-width: 80px;
}
QLabel {
    color: #ece6da;
}
QWidget#navRail {
    background: #2a2a2a;
    border-right: 1px solid #3d3d3d;
}
QWidget#navRail QLabel {
    color: #d8d0c4;
    font-weight: 600;
}
QWidget#hubPane {
    background: #1e1e1e;
}
QLabel#hubTitle {
    font-size: 28px;
    font-weight: 700;
    color: #f3eee4;
    padding: 8px 0 4px 0;
}
QWidget#hubPane QPushButton {
    font-size: 16px;
    padding: 14px 16px;
    min-height: 44px;
    text-align: left;
}
QComboBox, QCheckBox, QPushButton {
    font-size: 13px;
}
QPushButton {
    background: #3a3a3a;
    color: #f3eee4;
    border: 1px solid #4c4c4c;
    border-radius: 6px;
    padding: 7px 10px;
    text-align: left;
}
QPushButton:hover {
    background: #4a4a4a;
}
QPushButton:pressed, QPushButton:checked {
    background: #c9a227;
    color: #1e1e1e;
    border-color: #e0c36a;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    background: #353535;
    color: #f3eee4;
    border: 1px solid #4c4c4c;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #c9a227;
    selection-color: #1e1e1e;
}
QComboBox QAbstractItemView {
    background: #2f2f2f;
    color: #f3eee4;
    selection-background-color: #c9a227;
    selection-color: #1e1e1e;
    border: 1px solid #4c4c4c;
}
QCheckBox {
    color: #e6dfd3;
    spacing: 8px;
}
QLabel#gameStatus {
    font-size: 16px;
    font-weight: 700;
    padding: 6px 4px;
    color: #f3eee4;
}
QLabel#gameStatus[state="check"] { color: #e85d4c; }
QLabel#gameStatus[state="mate"] { color: #ff8a7a; }
QLabel#gameStatus[state="draw"] { color: #e0c36a; }
QLabel#gameStatus[state="win"] { color: #6dcb8b; }
QLabel#gameStatus[state="active"] { color: #f3eee4; }
QListWidget {
    background: #f7f2e8;
    alternate-background-color: #efe8d8;
    border: 1px solid #d4cbb8;
    border-radius: 8px;
    padding: 4px;
    font-size: 14px;
    color: #2a2a2a;
}
QListWidget::item:selected {
    background: #e8d56a;
    color: #1e1e1e;
}
QTableWidget#moveList {
    background: #f7f2e8;
    alternate-background-color: #efe8d8;
    border: 1px solid #d4cbb8;
    border-radius: 8px;
    padding: 4px;
    font-size: 14px;
    color: #2a2a2a;
    gridline-color: transparent;
    selection-background-color: #e8d56a;
    selection-color: #1e1e1e;
}
QTableWidget#moveList::item {
    padding: 2px 6px;
}
QTableWidget#moveList::item:selected {
    background: #e8d56a;
    color: #1e1e1e;
}
QTableWidget {
    background: #2a2a2a;
    color: #ece6da;
    gridline-color: #3d3d3d;
    border: 1px solid #3d3d3d;
    border-radius: 6px;
}
QTableWidget::item:selected {
    background: #c9a227;
    color: #1e1e1e;
}
QTabWidget::pane {
    border: 1px solid #3d3d3d;
    background: #1e1e1e;
    top: -1px;
    border-radius: 6px;
}
QTabBar::tab {
    background: #2a2a2a;
    color: #d8d0c4;
    padding: 8px 16px;
    border: 1px solid #3d3d3d;
    border-bottom: none;
    min-width: 88px;
}
QTabBar::tab:selected {
    background: #c9a227;
    color: #1e1e1e;
}
QTabBar::tab:hover:!selected {
    background: #3a3a3a;
}
QHeaderView::section {
    background: #353535;
    color: #ece6da;
    border: 1px solid #3d3d3d;
    padding: 4px;
}
QLabel#evalScore {
    font-size: 18px;
    font-weight: 700;
    color: #f3eee4;
}
QLabel#gameHint {
    color: #b9b0a3;
    font-size: 12px;
}
QLabel#panelTitle {
    color: #d8d0c4;
    font-weight: 600;
    padding-top: 4px;
}
QWidget#modePicker {
    background: transparent;
    color: #ece6da;
}
QScrollArea#modeOverlayScroll,
QScrollArea#modeOverlayScroll > QWidget > QWidget,
QWidget#modeOverlays {
    background: transparent;
    border: none;
}
QSplitter::handle {
    background: #3d3d3d;
    width: 6px;
}
QScrollBar:vertical {
    background: #2a2a2a;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #5a5a5a;
    min-height: 24px;
    border-radius: 4px;
}
QMessageBox {
    background: #2a2a2a;
    color: #ece6da;
}
QPushButton#themeToggle {
    min-width: 92px;
    padding: 6px 12px;
    text-align: center;
    font-size: 12px;
}
"""

LIGHT_STYLESHEET = """
QMainWindow, QWidget#rootPane, QStackedWidget, QDialog {
    background: #f4efe6;
    color: #2a261f;
}
QDialog QPushButton {
    text-align: center;
    min-width: 80px;
}
QLabel {
    color: #2a261f;
}
QWidget#navRail {
    background: #ebe4d4;
    border-right: 1px solid #d0c7b4;
}
QWidget#navRail QLabel {
    color: #3d382f;
    font-weight: 600;
}
QWidget#hubPane {
    background: #f4efe6;
}
QLabel#hubTitle {
    font-size: 28px;
    font-weight: 700;
    color: #1f1c18;
    padding: 8px 0 4px 0;
}
QWidget#hubPane QPushButton {
    font-size: 16px;
    padding: 14px 16px;
    min-height: 44px;
    text-align: left;
}
QComboBox, QCheckBox, QPushButton {
    font-size: 13px;
}
QPushButton {
    background: #fffaf1;
    color: #1f1c18;
    border: 1px solid #cfc6b4;
    border-radius: 6px;
    padding: 7px 10px;
    text-align: left;
}
QPushButton:hover {
    background: #efe6d4;
}
QPushButton:pressed, QPushButton:checked {
    background: #c9a227;
    color: #1e1e1e;
    border-color: #e0c36a;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {
    background: #fffef8;
    color: #1f1c18;
    border: 1px solid #cfc6b4;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #c9a227;
    selection-color: #1e1e1e;
}
QComboBox QAbstractItemView {
    background: #fffef8;
    color: #1f1c18;
    selection-background-color: #c9a227;
    selection-color: #1e1e1e;
    border: 1px solid #cfc6b4;
}
QCheckBox {
    color: #2a261f;
    spacing: 8px;
}
QLabel#gameStatus {
    font-size: 16px;
    font-weight: 700;
    padding: 6px 4px;
    color: #1f1c18;
}
QLabel#gameStatus[state="check"] { color: #c43c2d; }
QLabel#gameStatus[state="mate"] { color: #b13224; }
QLabel#gameStatus[state="draw"] { color: #8a7018; }
QLabel#gameStatus[state="win"] { color: #2f7a49; }
QLabel#gameStatus[state="active"] { color: #1f1c18; }
QListWidget {
    background: #fffef8;
    alternate-background-color: #f7f2e8;
    border: 1px solid #d4cbb8;
    border-radius: 8px;
    padding: 4px;
    font-size: 14px;
    color: #2a2a2a;
}
QListWidget::item:selected {
    background: #e8d56a;
    color: #1e1e1e;
}
QTableWidget#moveList {
    background: #fffef8;
    alternate-background-color: #f7f2e8;
    border: 1px solid #d4cbb8;
    border-radius: 8px;
    padding: 4px;
    font-size: 14px;
    color: #2a2a2a;
    gridline-color: transparent;
    selection-background-color: #e8d56a;
    selection-color: #1e1e1e;
}
QTableWidget#moveList::item {
    padding: 2px 6px;
}
QTableWidget#moveList::item:selected {
    background: #e8d56a;
    color: #1e1e1e;
}
QTableWidget {
    background: #fffef8;
    color: #2a261f;
    gridline-color: #d0c7b4;
    border: 1px solid #d0c7b4;
    border-radius: 6px;
}
QTableWidget::item:selected {
    background: #c9a227;
    color: #1e1e1e;
}
QTabWidget::pane {
    border: 1px solid #d0c7b4;
    background: #f4efe6;
    top: -1px;
    border-radius: 6px;
}
QTabBar::tab {
    background: #ebe4d4;
    color: #3d382f;
    padding: 8px 16px;
    border: 1px solid #d0c7b4;
    border-bottom: none;
    min-width: 88px;
}
QTabBar::tab:selected {
    background: #c9a227;
    color: #1e1e1e;
}
QTabBar::tab:hover:!selected {
    background: #efe6d4;
}
QHeaderView::section {
    background: #efe6d4;
    color: #2a261f;
    border: 1px solid #d0c7b4;
    padding: 4px;
}
QLabel#evalScore {
    font-size: 18px;
    font-weight: 700;
    color: #1f1c18;
}
QLabel#gameHint {
    color: #6d6558;
    font-size: 12px;
}
QLabel#panelTitle {
    color: #3d382f;
    font-weight: 600;
    padding-top: 4px;
}
QWidget#modePicker {
    background: transparent;
    color: #2a261f;
}
QScrollArea#modeOverlayScroll,
QScrollArea#modeOverlayScroll > QWidget > QWidget,
QWidget#modeOverlays {
    background: transparent;
    border: none;
}
QSplitter::handle {
    background: #d0c7b4;
    width: 6px;
}
QScrollBar:vertical {
    background: #ebe4d4;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #c4bba8;
    min-height: 24px;
    border-radius: 4px;
}
QMessageBox {
    background: #f4efe6;
    color: #2a261f;
}
QPushButton#themeToggle {
    min-width: 92px;
    padding: 6px 12px;
    text-align: center;
    font-size: 12px;
}
"""


class _ThemeController(QObject):
    changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.kind = ThemeKind.DARK


_CONTROLLER: _ThemeController | None = None


def theme_controller() -> _ThemeController:
    global _CONTROLLER
    if _CONTROLLER is None:
        _CONTROLLER = _ThemeController()
    return _CONTROLLER


def current_theme() -> ThemeKind:
    return theme_controller().kind


def stylesheet_for(kind: ThemeKind) -> str:
    return LIGHT_STYLESHEET if kind is ThemeKind.LIGHT else SHELL_STYLESHEET


def notation_ink(kind: ThemeKind | None = None) -> QColor:
    """Coordinate letters: white on the dark shell, dark ink on the light shell."""
    active = current_theme() if kind is None else kind
    if active is ThemeKind.LIGHT:
        return QColor(36, 32, 28)
    return QColor(255, 255, 255)


def apply_theme(kind: ThemeKind, *, persist: bool | None = None) -> ThemeKind:
    controller = theme_controller()
    controller.kind = kind
    app = QApplication.instance()
    if isinstance(app, QApplication):
        app.setStyleSheet(stylesheet_for(kind))
    if persist is None:
        persist = "pytest" not in sys.modules
    if persist:
        settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        settings.setValue(_SETTINGS_KEY, kind.value)
    controller.changed.emit(kind)
    return kind


def toggle_theme(*, persist: bool | None = None) -> ThemeKind:
    nxt = ThemeKind.LIGHT if current_theme() is ThemeKind.DARK else ThemeKind.DARK
    return apply_theme(nxt, persist=persist)


def load_saved_theme() -> ThemeKind:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    raw = str(settings.value(_SETTINGS_KEY, ThemeKind.DARK.value))
    return ThemeKind.LIGHT if raw == ThemeKind.LIGHT.value else ThemeKind.DARK


def apply_saved_theme() -> ThemeKind:
    return apply_theme(load_saved_theme(), persist=False)


def sync_theme_button(button: QPushButton) -> None:
    light = current_theme() is ThemeKind.LIGHT
    button.blockSignals(True)
    button.setChecked(light)
    button.setText("Тёмная" if light else "Светлая")
    button.blockSignals(False)


class ThemeToggleButton(QPushButton):
    """Corner control that dies with the window and unsubscribes from the theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("themeToggle")
        self.setCheckable(True)
        self.setToolTip(f"Светлая / тёмная тема ({THEME_SHORTCUT})")
        sync_theme_button(self)
        self.clicked.connect(self._on_clicked)
        theme_controller().changed.connect(self._on_theme_changed)

    def _on_clicked(self, _checked: bool = False) -> None:
        toggle_theme()

    def _on_theme_changed(self, _kind: object = None) -> None:
        sync_theme_button(self)


def make_theme_toggle_button(parent: QWidget | None = None) -> QPushButton:
    return ThemeToggleButton(parent)


MODE_LABELS = {
    "chess": "Классика",
    "classic_chess": "Классика",
    "chess960": "Chess960",
    "crazyhouse": "Crazyhouse",
    "bughouse": "Bughouse",
    "hand_and_brain": "Hand & Brain",
    "giveaway": "Giveaway",
    "minichess": "Мини-шахматы",
    "cylindrical": "Цилиндрические",
    "duck": "Duck chess",
    "shogi": "Сёги",
    "kyoto_shogi": "Киото-сёги",
    "dobutsu_shogi": "Добуцу-сёги",
    "reversi": "Реверси",
    "corners": "Уголки",
    "draughts": "Русские шашки",
    "nanai_checkers": "Нанайские шашки",
    "gobblet": "Gobblet Gobblers",
    "hasami_shogi": "Хасами сёги",
    "fairy": "Fairytale",
    "fairytale": "Fairytale",
}


def mode_display_name(mode_id: str) -> str:
    if mode_id in MODE_LABELS:
        return MODE_LABELS[mode_id]
    try:
        from chess_core.modes.orchestrator import parse_spec, spec_display_name

        return spec_display_name(parse_spec(mode_id))
    except ValueError:
        return mode_id


def toggle_fullscreen(window: QWidget) -> None:
    """Enter or leave true fullscreen (no title bar)."""
    if window.isFullScreen():
        window.showNormal()
    else:
        window.showFullScreen()


def exit_fullscreen(window: QWidget) -> None:
    if window.isFullScreen():
        window.showNormal()


class FullscreenMainWindow(QMainWindow):
    """Main window with F11 fullscreen; Escape leaves it only while fullscreen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        toggle = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        toggle.setContext(Qt.ShortcutContext.WindowShortcut)
        toggle.activated.connect(self.toggle_fullscreen)
        self._fullscreen_escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._fullscreen_escape.setContext(Qt.ShortcutContext.WindowShortcut)
        self._fullscreen_escape.setEnabled(False)
        self._fullscreen_escape.activated.connect(self.exit_fullscreen)
        self._theme_shortcut = QShortcut(QKeySequence(THEME_SHORTCUT), self)
        self._theme_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._theme_shortcut.activated.connect(self.toggle_theme)
        self.theme_button = make_theme_toggle_button(self)

    def toggle_fullscreen(self) -> None:
        toggle_fullscreen(self)

    def exit_fullscreen(self) -> None:
        exit_fullscreen(self)

    def toggle_theme(self) -> None:
        toggle_theme()

    def changeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        if event.type() == QEvent.Type.WindowStateChange:
            self._fullscreen_escape.setEnabled(self.isFullScreen())
        super().changeEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        super().resizeEvent(event)
        self._place_theme_button()

    def showEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        super().showEvent(event)
        self._place_theme_button()

    def _place_theme_button(self) -> None:
        button = getattr(self, "theme_button", None)
        if button is None or button.parent() is not self:
            return
        button.adjustSize()
        margin = 12
        button.move(
            self.width() - button.width() - margin,
            self.height() - button.height() - margin,
        )
        button.raise_()


def tighten_wrapping_label(label: QLabel) -> QLabel:
    """Wrap long copy without letting its unwrapped width stretch the window."""
    label.setWordWrap(True)
    policy = label.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
    label.setSizePolicy(policy)
    return label


def app_icon(assets: AssetsLoader | None = None, size: int = 64) -> QIcon:
    """Window and shortcut icon: white knight on a dark square."""
    loader = assets or AssetsLoader()
    ico_path = loader.assets_root / "ui" / "app.ico"
    if ico_path.is_file():
        return QIcon(str(ico_path))
    renderer = QSvgRenderer(str(loader.chess_piece_path("wN")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(Qt.GlobalColor.transparent)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
