"""Paste-and-review PGN page with disposable analysis branches."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from chess_core.core.gamemode import GameMode
from chess_core.ui.local_game import LocalGameWidget


class PgnViewerWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pgn_text = QPlainTextEdit()
        self.pgn_text.setPlaceholderText(
            "Вставьте сюда содержимое PGN-файла, затем нажмите «Загрузить PGN»."
        )
        self.pgn_text.setMaximumHeight(170)
        self.load_button = QPushButton("Загрузить PGN")
        self.clear_button = QPushButton("Очистить")
        self.hint = QLabel(
            "Выберите режим игры слева до загрузки. Можно открыть прошлый ход и "
            "подвигать фигуры: временная ветка удаляется кнопкой возврата к основной линии."
        )
        self.hint.setWordWrap(True)

        paste_controls = QHBoxLayout()
        paste_controls.addWidget(self.load_button)
        paste_controls.addWidget(self.clear_button)
        paste_controls.addStretch()

        self.game = LocalGameWidget(
            mode_resolver,
            mode_id,
            allow_temporary_variations=True,
            include_initial_position=True,
            show_clock=False,
        )
        self.game.new_game_button.hide()
        self.game.quit_button.hide()
        self.game.instructions.setText(
            "Клик по записи открывает позицию. Из архивной позиции можно начать "
            "временную ветку; ←/→ переключают полуходы; "
            "«Вернуться к основной линии» удаляет ветку."
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self.hint)
        layout.addWidget(self.pgn_text)
        layout.addLayout(paste_controls)
        layout.addWidget(self.game, 1)

        self.load_button.clicked.connect(self.load_pgn)
        self.clear_button.clicked.connect(self.pgn_text.clear)

    def set_mode(self, mode_id: str) -> None:
        self.game.set_mode(mode_id)

    def reload_piece_assets(self) -> None:
        self.game.reload_piece_assets()

    def load_pgn(self) -> bool:
        text = self.pgn_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "PGN не загружен", "Вставьте содержимое PGN.")
            return False
        try:
            self.game.load_pgn(text)
        except (RuntimeError, ValueError) as error:
            QMessageBox.critical(
                self,
                "Не удалось загрузить PGN",
                f"{error}\n\nПроверьте, что слева выбран правильный режим игры.",
            )
            return False
        self.game.status.setText("PGN загружен. Выберите ход в записи для просмотра.")
        return True
