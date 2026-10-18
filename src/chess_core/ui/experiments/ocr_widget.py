"""Scoresheet OCR experiment: one full-size stage window after another."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.experiments.ocr import (
    ocr_project_root,
    pick_random_input,
    run_scoresheet_pipeline,
)
from chess_core.app.experiments.ocr_stage12 import raw_scoresheet_images
from chess_core.ui.theme import tighten_wrapping_label


class ScoresheetOcrWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel("Бланк → этапы по одному окну")
        title.setObjectName("panelTitle")
        ocr_root = ocr_project_root()
        photos = raw_scoresheet_images()
        self.hint = QLabel(
            "Каждый этап открывается на весь экран. Закройте окно — появится следующий: "
            "выравнивание, шапка/таблица, сетка, MSER, 28×28, CNN. "
            "Терминал: python -m chess_core.tools.demo_glyph_ocr [--input image_0006.jpg]."
        )
        tighten_wrapping_label(self.hint)
        extra = (
            f"Реальные бланки: {len(photos)} шт. в {ocr_root / 'data' / 'raw'}"
            if ocr_root is not None
            else "Соседний OCR-проект не найден — сетку stage12 запустить нельзя."
        )
        self.external = QLabel(extra)
        tighten_wrapping_label(self.external)

        self.random_button = QPushButton("Случайный бланк")
        self.choose_button = QPushButton("Открыть бланк…")
        self.random_button.clicked.connect(self._run_random)
        self.choose_button.clicked.connect(self._choose_image)
        controls = QHBoxLayout()
        controls.addWidget(self.random_button)
        controls.addWidget(self.choose_button)
        controls.addStretch()

        self.status = QLabel(
            "Нажмите «Случайный бланк» или выберите файл — откроется первое окно этапа."
        )
        tighten_wrapping_label(self.status)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.hint)
        layout.addWidget(self.external)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addStretch()

    def _choose_image(self) -> None:
        start = ocr_project_root()
        start_dir = str(start / "data" / "raw") if start is not None else ""
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Бланк партии",
            start_dir,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*.*)",
        )
        if path:
            self._run(Path(path))

    def _run_random(self) -> None:
        try:
            self._run(pick_random_input())
        except FileNotFoundError as exc:
            self.status.setText(str(exc))

    def _run(self, path: Path) -> None:
        try:
            run = run_scoresheet_pipeline(path)
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            self.status.setText(str(exc))
            return
        self.status.setText(
            f"Вход: {run.source.name}  ·  {run.engine}  ·  "
            f"сетка {run.grid_rows}x{run.grid_cols}  ·  занято {run.occupied_cells}  ·  "
            f"этапов {len(run.stages)}  ·  закрывайте окно, чтобы идти дальше"
        )
        from chess_core.ui.experiments.ocr_stages import play_scoresheet_stages

        play_scoresheet_stages(run, self)
