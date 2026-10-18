"""Experiments branch: Elo modeling and scoresheet OCR."""

from __future__ import annotations

from chess_core.ui.shell import BranchWindow, PageSpec


class ExperimentsWindow(BranchWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Chess Core — Эксперименты",
            (
                PageSpec("Эло", self._make_elo),
                PageSpec("Бланки", self._make_ocr),
            ),
            show_mode_picker=False,
            parent=parent,
        )

    def _make_elo(self):
        from chess_core.ui.experiments.elo_widget import EloExperimentWidget

        return EloExperimentWidget()

    def _make_ocr(self):
        from chess_core.ui.experiments.ocr_widget import ScoresheetOcrWidget

        return ScoresheetOcrWidget()
