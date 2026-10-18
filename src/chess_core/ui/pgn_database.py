"""PGN database page: combine saved games into a ChessBase 16 .pgn file."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.pgn_database import PgnDatabaseService, SourcedPgnGame, default_database_filename
from chess_core.infra.storage.pgn_files import (
    default_games_dir,
    load_folder_texts,
    read_pgn_text,
    write_chessbase_pgn,
)
from chess_core.ui.theme import tighten_wrapping_label


class PgnDatabaseWidget(QWidget):
    """Collect .pgn/.txt games from a folder and write a ChessBase PGN database."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = PgnDatabaseService()
        self._folder: Path | None = None
        self._games: tuple[SourcedPgnGame, ...] = ()

        title = QLabel("Базы партий")
        title.setObjectName("panelTitle")
        self.hint = QLabel(
            "Соберите сохранённые партии (.pgn или .txt) в одну PGN-базу. "
            "ChessBase 16 открывает такой файл через «Файл → Открыть базу» "
            "(тип PGN). Кодировка UTF-8 с BOM, строки CRLF."
        )
        tighten_wrapping_label(self.hint)

        self.folder_label = QLabel("Папка не выбрана.")
        tighten_wrapping_label(self.folder_label)
        self.choose_folder = QPushButton("Папка с партиями…")
        self.recursive = QCheckBox("Включая подпапки")
        self.refresh = QPushButton("Обновить")
        self.create_database = QPushButton("Создать базу…")
        self.append_database = QPushButton("Добавить в базу…")
        self.create_database.setEnabled(False)
        self.append_database.setEnabled(False)
        self.refresh.setEnabled(False)

        self.games_table = QTableWidget(0, 6)
        self.games_table.setObjectName("pgnDatabaseList")
        self.games_table.setHorizontalHeaderLabels(
            ("Белые", "Чёрные", "Результат", "Дата", "Событие", "Файл")
        )
        self.games_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.games_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.games_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.games_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.status = QLabel("Выберите папку с сохранёнными партиями.")
        tighten_wrapping_label(self.status)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.hint)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.choose_folder)
        folder_row.addWidget(self.recursive)
        folder_row.addWidget(self.refresh)
        folder_row.addStretch()
        layout.addLayout(folder_row)
        layout.addWidget(self.folder_label)
        actions = QHBoxLayout()
        actions.addWidget(self.create_database)
        actions.addWidget(self.append_database)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(self.games_table, 1)
        layout.addWidget(self.status)

        self.choose_folder.clicked.connect(self._choose_folder)
        self.refresh.clicked.connect(self._reload)
        self.recursive.toggled.connect(self._reload)
        self.create_database.clicked.connect(self._create_database)
        self.append_database.clicked.connect(self._append_database)

    @property
    def games(self) -> tuple[SourcedPgnGame, ...]:
        return self._games

    def load_folder(self, folder: Path, *, recursive: bool | None = None) -> int:
        self._folder = folder
        if recursive is not None:
            self.recursive.setChecked(recursive)
        self.folder_label.setText(str(folder))
        self.refresh.setEnabled(True)
        return self._reload()

    def write_new_database(self, path: Path) -> int:
        text = self._service.create_database(self._games)
        write_chessbase_pgn(path, text)
        count = len(self._service.parse_text(text))
        self.status.setText(
            f"Создана база {path.name}: {count} партий. Откройте файл в ChessBase 16."
        )
        return count

    def append_to_database(self, path: Path) -> int:
        extra = tuple(item.game for item in self._games)
        existing = read_pgn_text(path) if path.is_file() else ""
        text = self._service.append_to_database(existing, extra)
        write_chessbase_pgn(path, text)
        added = self._service.added_count(existing, text)
        total = len(self._service.parse_text(text))
        self.status.setText(
            f"В {path.name} добавлено партий: {added}. Всего в базе: {total}."
        )
        return added

    def _choose_folder(self) -> None:
        start = str(self._folder or default_games_dir())
        chosen = QFileDialog.getExistingDirectory(self, "Папка с сохранёнными партиями", start)
        if not chosen:
            return
        self.load_folder(Path(chosen))

    def _reload(self) -> int:
        if self._folder is None:
            return 0
        if not self._folder.is_dir():
            self._games = ()
            self._fill_table()
            self.status.setText("Папка не найдена.")
            return 0
        try:
            items = load_folder_texts(
                self._folder,
                recursive=self.recursive.isChecked(),
            )
        except OSError as exc:
            self.status.setText(str(exc))
            return 0
        self._games = self._service.collect_from_texts(items)
        self._fill_table()
        files = len(items)
        games = len(self._games)
        self.create_database.setEnabled(games > 0)
        self.append_database.setEnabled(games > 0)
        if games == 0:
            self.status.setText(
                f"В папке нет партий (.pgn / .txt). Найдено файлов: {files}."
            )
        else:
            self.status.setText(f"Найдено партий: {games} в файлах: {files}.")
        return games

    def _create_database(self) -> None:
        if not self._games:
            return
        suggested = str((self._folder or default_games_dir()) / default_database_filename())
        chosen, _filter = QFileDialog.getSaveFileName(
            self,
            "Создать PGN-базу для ChessBase",
            suggested,
            "База ChessBase / PGN (*.pgn);;Все файлы (*.*)",
        )
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() != ".pgn":
            path = path.with_suffix(".pgn")
        try:
            self.write_new_database(path)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось записать базу", str(exc))

    def _append_database(self) -> None:
        if not self._games:
            return
        start = str(self._folder or default_games_dir())
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            "Добавить партии в существующую PGN-базу",
            start,
            "База ChessBase / PGN (*.pgn);;Все файлы (*.*)",
        )
        if not chosen:
            return
        path = Path(chosen)
        try:
            self.append_to_database(path)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось обновить базу", str(exc))

    def _fill_table(self) -> None:
        self.games_table.setRowCount(len(self._games))
        for row, item in enumerate(self._games):
            game = item.game
            values = (
                game.white,
                game.black,
                game.result,
                game.date,
                game.event,
                item.source,
            )
            for column, value in enumerate(values):
                self.games_table.setItem(row, column, QTableWidgetItem(value))
