"""Lightweight presentation theme for the desktop shell."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from chess_core.ui.assets_loader import AssetsLoader

SHELL_STYLESHEET = """
QMainWindow, QWidget#rootPane {
    background: #1e1e1e;
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
QComboBox, QSpinBox, QDoubleSpinBox {
    background: #353535;
    color: #f3eee4;
    border: 1px solid #4c4c4c;
    border-radius: 6px;
    padding: 4px 8px;
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
"""

MODE_LABELS: dict[str, str] = {
    "chess": "Классика",
    "chess960": "Chess960",
    "crazyhouse": "Crazyhouse",
    "giveaway": "Giveaway (заглушка)",
    "minichess": "Мини-шахматы (заглушка)",
    "cylindrical": "Цилиндрические",
    "duck": "Duck chess",
    "two_move": "Двухходовки",
    "fairytale": "Fairytale",
    "three_check": "Три шаха",
    "king_of_the_hill": "Царь горы",
    "three_check_king_of_the_hill": "Три шаха + царь горы",
    "shogi": "Сёги",
    "minishogi": "Мини-сёги",
    "kyoto_shogi": "Киото-сёги",
    "dobutsu_shogi": "Добуцу-сёги",
    "checkers": "Шашки",
    "corners": "Уголки",
    "gobblet": "Gobblet Gobblers",
    "gobblet+relocate": "Gobblet Gobblers (с ходами)",
    "gomoku": "Гомоку",
    "reversi": "Реверси",
}


def mode_display_name(mode_id: str) -> str:
    """Human-readable label for a registered or composed mode id."""
    if mode_id in MODE_LABELS:
        return MODE_LABELS[mode_id]
    if mode_id.startswith("chess+"):
        parts = [MODE_LABELS.get(part, part) for part in mode_id.split("+")[1:]]
        return " + ".join(parts) if parts else MODE_LABELS["chess"]
    if "+" in mode_id:
        base, rest = mode_id.split("+", 1)
        if base in MODE_LABELS:
            return f"{MODE_LABELS[base]} ({rest})"
    return mode_id


def app_icon(assets: AssetsLoader | None = None, size: int = 64) -> QIcon:
    """Window icon from the packaged Cburnett knight SVG."""
    loader = assets or AssetsLoader()
    renderer = QSvgRenderer(str(loader.chess_piece_path("wN")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
