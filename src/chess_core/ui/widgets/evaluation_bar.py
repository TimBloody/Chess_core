"""Engine evaluation bar (presentation only)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chess_core.app.engine import EngineEvaluation


class EvaluationBarWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bar = QLabel("0.0")
        self._detail = QLabel("")
        layout = QVBoxLayout(self)
        layout.addWidget(self._bar)
        layout.addWidget(self._detail)

    def set_evaluation(self, evaluation: EngineEvaluation | None, *, error: str | None = None) -> None:
        if error:
            self._bar.setText("—")
            self._detail.setText(error)
            return
        if evaluation is None:
            self._bar.setText("—")
            self._detail.setText("No engine")
            return
        if evaluation.mate_in is not None:
            sign = "+" if evaluation.mate_in > 0 else "-"
            self._bar.setText(f"M{abs(evaluation.mate_in)}")
            self._detail.setText(f"Mate {sign}")
            return
        if evaluation.score_cp is not None:
            pawns = evaluation.score_cp / 100.0
            self._bar.setText(f"{pawns:+.1f}")
            pv = " ".join(evaluation.pv[:3])
            self._detail.setText(pv or f"depth {evaluation.depth or '?'}")
            return
        self._bar.setText("—")
        self._detail.setText("")
