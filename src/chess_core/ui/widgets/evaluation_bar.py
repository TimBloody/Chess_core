"""Engine evaluation bar (presentation only)."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chess_core.app.engine import EngineEvaluation

_WHITE = QColor(236, 232, 220)
_BLACK = QColor(36, 36, 36)
_BORDER = QColor(90, 82, 68)


class EvaluationBarWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._white_share = 0.5
        self._bar = QLabel("0.0")
        self._detail = QLabel("")
        self._bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bar.setObjectName("evalScore")
        self._detail.setObjectName("evalDetail")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._bar)
        layout.addWidget(self._detail)
        self.setMinimumHeight(56)

    def set_evaluation(self, evaluation: EngineEvaluation | None, *, error: str | None = None) -> None:
        if error:
            self._bar.setText("—")
            self._detail.setText(error)
            self._set_share(0.5)
            return
        if evaluation is None:
            self._bar.setText("—")
            self._detail.setText("")
            self._set_share(0.5)
            return
        if evaluation.mate_in is not None:
            sign = "+" if evaluation.mate_in > 0 else "-"
            self._bar.setText(f"M{abs(evaluation.mate_in)}")
            self._detail.setText(f"Mate {sign}")
            self._set_share(1.0 if evaluation.mate_in > 0 else 0.0)
            return
        if evaluation.score_cp is not None:
            pawns = evaluation.score_cp / 100.0
            self._bar.setText(f"{pawns:+.1f}")
            pv = " ".join(evaluation.pv[:3])
            self._detail.setText(pv or f"depth {evaluation.depth or '?'}")
            self._set_share(max(0.04, min(0.96, 0.5 + evaluation.score_cp / 1600.0)))
            return
        self._bar.setText("—")
        self._detail.setText("")
        self._set_share(0.5)

    def paintEvent(self, event) -> None:  # noqa: ANN001 - Qt override signature
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        meter = QRectF(0, 2, self.width(), 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BLACK)
        painter.drawRoundedRect(meter, 4, 4)
        white_width = meter.width() * self._white_share
        if white_width > 0:
            painter.setBrush(_WHITE)
            painter.drawRoundedRect(
                QRectF(meter.left(), meter.top(), white_width, meter.height()),
                4,
                4,
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_BORDER)
        painter.drawRoundedRect(meter, 4, 4)

    def _set_share(self, share: float) -> None:
        clamped = max(0.0, min(1.0, share))
        if clamped != self._white_share:
            self._white_share = clamped
            self.update()
        else:
            self.update()
