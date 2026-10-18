"""One full-size window per scoresheet OCR stage; next opens after close."""

from __future__ import annotations

from collections.abc import Callable
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.experiments.ocr import OcrRun
from chess_core.ui.theme import SHELL_STYLESHEET, app_icon, tighten_wrapping_label

_QT_APP: QApplication | None = None


def ensure_qt_app() -> QApplication:
    """Keep a live QApplication; constructing one without a name lets GC kill it."""

    global _QT_APP
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        _QT_APP = existing
        return existing
    _QT_APP = QApplication(sys.argv)
    return _QT_APP


class ScoresheetStageDialog(QDialog):
    """Single stage at a readable size. Closing it means 'next'."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowIcon(app_icon())
        self.setStyleSheet(SHELL_STYLESHEET)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.aborted = False
        self._pixmap = QPixmap()

        self.heading = QLabel()
        self.heading.setObjectName("panelTitle")
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heading.setWordWrap(True)

        self.hint = QLabel()
        self.hint.setObjectName("gameHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        tighten_wrapping_label(self.hint)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(900, 560)
        self.image.setStyleSheet(
            "background: #141414; border: 1px solid #3d3d3d; border-radius: 6px;"
        )

        self.caption = QLabel()
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        tighten_wrapping_label(self.caption)

        self.reads = QPlainTextEdit()
        self.reads.setReadOnly(True)
        self.reads.setMaximumHeight(160)
        self.reads.hide()

        next_button = QPushButton("Дальше")
        next_button.setDefault(True)
        next_button.clicked.connect(self.accept)
        stop_button = QPushButton("Прервать")
        stop_button.clicked.connect(self._abort)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(stop_button)
        buttons.addWidget(next_button)

        root = QWidget()
        root.setObjectName("rootPane")
        layout = QVBoxLayout(root)
        layout.addWidget(self.heading)
        layout.addWidget(self.hint)
        layout.addWidget(self.image, 1)
        layout.addWidget(self.caption)
        layout.addWidget(self.reads)
        layout.addLayout(buttons)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

    def present(self, run: OcrRun, index: int) -> None:
        total = len(run.stages)
        stage = run.stages[index]
        last = index + 1 >= total
        self.setWindowTitle(f"OCR бланка — {index + 1}/{total} — {stage.title}")
        self.heading.setText(f"{stage.title}   ·   этап {index + 1} из {total}")
        if last:
            self.hint.setText("Последний этап. Закройте окно, когда посмотрите.")
        else:
            self.hint.setText("Закройте окно — откроется следующий этап.")
        self.caption.setText(stage.note)
        self._pixmap = QPixmap(str(stage.path))
        missing = self._pixmap.isNull()
        if missing:
            self.image.setText("нет картинки\nэтот этап не прошёл")
            self.caption.setStyleSheet("color: #e8b4b4;")
        else:
            self.image.setText("")
            self.caption.setStyleSheet("")
        if last or stage.key == "10_cnn_glyphs.png":
            self.reads.show()
            if run.cell_reads:
                self.reads.setPlainText(
                    "\n".join(
                        f"{n + 1:02d}.  {text or '—'}"
                        for n, text in enumerate(run.cell_reads)
                    )
                )
            else:
                extra = "\n".join(note for note in run.notes if note)
                self.reads.setPlainText(extra or "CNN не прочитал клетки.")
        else:
            self.reads.hide()
        self._fit_to_screen()
        self._fit_image()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_image()

    def _fit_to_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            self.resize(1200, 800)
            return
        area = screen.availableGeometry()
        self.resize(max(900, int(area.width() * 0.88)), max(640, int(area.height() * 0.88)))

    def _fit_image(self) -> None:
        if self._pixmap.isNull():
            return
        size = self.image.size()
        if size.width() < 8 or size.height() < 8:
            return
        self.image.setPixmap(
            self._pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _abort(self) -> None:
        self.aborted = True
        self.reject()


def play_scoresheet_stages(
    run: OcrRun,
    parent: QWidget | None = None,
    *,
    exec_dialog: Callable[[ScoresheetStageDialog], object] | None = None,
) -> None:
    """Show stages one window at a time. Next window opens after the previous closes."""

    ensure_qt_app()
    owner = parent.window() if parent is not None else None
    closer = exec_dialog or _run_dialog
    for index in range(len(run.stages)):
        dialog = ScoresheetStageDialog(owner)
        dialog.present(run, index)
        closer(dialog)
        if dialog.aborted:
            break


def _run_dialog(dialog: ScoresheetStageDialog) -> None:
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.exec()
