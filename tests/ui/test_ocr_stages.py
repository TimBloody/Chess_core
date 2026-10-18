"""Stage windows open one after another; next after close."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.experiments.ocr import OcrRun, OcrStage
from chess_core.ui.experiments.ocr_stages import (
    ScoresheetStageDialog,
    ensure_qt_app,
    play_scoresheet_stages,
)

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _run(tmp_path: Path) -> OcrRun:
    dummy = tmp_path / "01_deskewed.jpg"
    dummy.write_bytes(b"not-an-image")
    return OcrRun(
        source=tmp_path / "blank.jpg",
        output_dir=tmp_path,
        stages=(
            OcrStage("01_deskewed.jpg", "2. Выравнивание", dummy, "лист должен быть прямым"),
            OcrStage("02_split_overlay.jpg", "3. Шапка / таблица", dummy, "граница"),
            OcrStage("08_mser_glyphs.jpg", "8. MSER", dummy, "рамки"),
            OcrStage("10_cnn_glyphs.png", "10. CNN", dummy, "подписи"),
        ),
        moves=(),
        pgn="",
        pgn_path=tmp_path / "glyphs.json",
        engine="mser+cnn",
        cell_reads=("e4", "e5"),
    )


def test_ensure_qt_app_keeps_the_application() -> None:
    app = ensure_qt_app()
    assert QApplication.instance() is app


def test_dialog_shows_one_stage_at_a_time(tmp_path: Path) -> None:
    _app()
    run = _run(tmp_path)
    dialog = ScoresheetStageDialog()
    dialog.present(run, 0)
    assert "Выравнивание" in dialog.windowTitle()
    assert "1 из 4" in dialog.heading.text()
    assert "следующий этап" in dialog.hint.text()
    assert dialog.reads.isHidden()
    dialog.present(run, 3)
    assert "CNN" in dialog.windowTitle()
    assert "4 из 4" in dialog.heading.text()
    assert not dialog.reads.isHidden()
    assert "e4" in dialog.reads.toPlainText()
    dialog.close()


def test_closing_advances_through_all_stages(tmp_path: Path) -> None:
    _app()
    run = _run(tmp_path)
    seen: list[str] = []

    def close_immediately(dialog: ScoresheetStageDialog) -> None:
        seen.append(dialog.heading.text())
        dialog.accept()

    play_scoresheet_stages(run, exec_dialog=close_immediately)
    assert len(seen) == 4
    assert "Выравнивание" in seen[0]
    assert "Шапка / таблица" in seen[1]
    assert "MSER" in seen[2]
    assert "CNN" in seen[3]


def test_abort_stops_the_sequence(tmp_path: Path) -> None:
    _app()
    run = _run(tmp_path)
    seen: list[str] = []

    def abort_first(dialog: ScoresheetStageDialog) -> None:
        seen.append(dialog.heading.text())
        dialog.aborted = True

    play_scoresheet_stages(run, exec_dialog=abort_first)
    assert len(seen) == 1
