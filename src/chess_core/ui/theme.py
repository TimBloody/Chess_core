"""Lightweight presentation theme for the desktop shell."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from chess_core.ui.assets_loader import AssetsLoader

SHELL_STYLESHEET = """
QMainWindow, QWidget#rootPane, QStackedWidget {
    background: #1e1e1e;
    color: #ece6da;
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
QLabel#evalDetail {
    color: #b9b0a3;
    font-size: 12px;
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
"""

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
}


def mode_display_name(mode_id: str) -> str:
    return MODE_LABELS.get(mode_id, mode_id)


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
