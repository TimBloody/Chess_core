"""Render labelled scoresheet fixtures for the OCR experiment."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QTransform,
)

SHEET_WIDTH = 520
SHEET_HEIGHT = 800
MARGIN = 28
HEADER_BOTTOM = 96
MOVE_ROWS = 20
NUMBER_COL = 40


def ensure_gui() -> None:
    if QApplication.instance() is None:
        QApplication([])


def _move_font() -> QFont:
    for family in ("Segoe Script", "Comic Sans MS", "Times New Roman"):
        font = QFont(family, 13)
        if QFont(family).exactMatch() or family == "Times New Roman":
            font.setItalic(family != "Segoe Script")
            return font
    font = QFont()
    font.setPointSize(13)
    font.setItalic(True)
    return font


def scoresheet_grid() -> dict[str, float | int]:
    table_top = HEADER_BOTTOM
    table_height = SHEET_HEIGHT - MARGIN - table_top
    cell_h = table_height / MOVE_ROWS
    move_width = (SHEET_WIDTH - 2 * MARGIN - NUMBER_COL) / 2
    return {
        "left": MARGIN,
        "top": table_top,
        "number_width": NUMBER_COL,
        "move_width": move_width,
        "cell_height": cell_h,
        "rows": MOVE_ROWS,
    }


def render_scoresheet(
    moves: Sequence[str],
    *,
    white: str = "White",
    black: str = "Black",
    event: str = "OCR fixture",
    rotate_deg: float = 0.0,
) -> QImage:
    """Draw a cream 20×2 scoresheet and optionally rotate it."""

    ensure_gui()
    image = QImage(SHEET_WIDTH, SHEET_HEIGHT, QImage.Format.Format_RGB32)
    image.fill(QColor("#f3e6c9"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    header = QFont("Segoe UI", 14, QFont.Weight.Bold)
    small = QFont("Segoe UI", 10)
    painter.setFont(header)
    painter.setPen(QColor("#1e1e1e"))
    painter.drawText(
        QRect(MARGIN, 16, SHEET_WIDTH - 2 * MARGIN, 28),
        Qt.AlignmentFlag.AlignHCenter,
        "ПРОТОКОЛ ПАРТИИ",
    )
    painter.setFont(small)
    painter.drawText(MARGIN, 58, f"Турнир: {event}")
    painter.drawText(MARGIN, 78, f"Белые: {white}")
    painter.drawText(SHEET_WIDTH // 2, 78, f"Чёрные: {black}")

    grid = scoresheet_grid()
    left = float(grid["left"])
    top = float(grid["top"])
    number_width = float(grid["number_width"])
    move_width = float(grid["move_width"])
    cell_h = float(grid["cell_height"])
    table_right = left + number_width + 2 * move_width
    table_bottom = top + MOVE_ROWS * cell_h

    painter.setPen(QPen(QColor("#3a2f1c"), 1.6))
    painter.drawRect(int(left), int(top), int(table_right - left), int(table_bottom - top))
    painter.drawLine(int(left + number_width), int(top), int(left + number_width), int(table_bottom))
    painter.drawLine(
        int(left + number_width + move_width),
        int(top),
        int(left + number_width + move_width),
        int(table_bottom),
    )
    for row in range(1, MOVE_ROWS):
        y = int(top + row * cell_h)
        painter.drawLine(int(left), y, int(table_right), y)

    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
    painter.drawText(QRect(int(left), int(top - 16), int(number_width), 16), Qt.AlignmentFlag.AlignCenter, "№")
    painter.drawText(
        QRect(int(left + number_width), int(top - 16), int(move_width), 16),
        Qt.AlignmentFlag.AlignCenter,
        "Белые",
    )
    painter.drawText(
        QRect(int(left + number_width + move_width), int(top - 16), int(move_width), 16),
        Qt.AlignmentFlag.AlignCenter,
        "Чёрные",
    )

    move_font = _move_font()
    for row in range(MOVE_ROWS):
        y = int(top + row * cell_h)
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(
            QRect(int(left), y, int(number_width), int(cell_h)),
            Qt.AlignmentFlag.AlignCenter,
            str(row + 1),
        )
        painter.setFont(move_font)
        white_ply = moves[row * 2] if row * 2 < len(moves) else ""
        black_ply = moves[row * 2 + 1] if row * 2 + 1 < len(moves) else ""
        painter.drawText(
            QRect(int(left + number_width + 6), y, int(move_width - 10), int(cell_h)),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            white_ply,
        )
        painter.drawText(
            QRect(int(left + number_width + move_width + 6), y, int(move_width - 10), int(cell_h)),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            black_ply,
        )
    painter.end()

    if abs(rotate_deg) < 0.05:
        return image
    rotated = image.transformed(QTransform().rotate(rotate_deg), Qt.TransformationMode.SmoothTransformation)
    canvas = QImage(rotated.size(), QImage.Format.Format_RGB32)
    canvas.fill(QColor("#d8c7a2"))
    painter = QPainter(canvas)
    painter.drawImage(0, 0, rotated)
    painter.end()
    return canvas
