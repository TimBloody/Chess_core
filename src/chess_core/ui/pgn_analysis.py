"""Paste, open, browse multi-game PGN, and analyse on the board."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.pgn_replay import looks_like_pgn
from chess_core.app.position_search import PositionHit, PositionIndex, build_position_index
from chess_core.core.gamemode import GameMode
from chess_core.core.pgn import PgnGame, parse_pgn
from chess_core.core.state import GameState
from chess_core.infra.storage.pgn_files import read_pgn_text
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.theme import tighten_wrapping_label

_GAMES_COLUMNS = ("№", "Белые", "Чёрные", "Рез.", "Дата", "Раунд", "ECO", "Событие")


class PgnAnalysisWidget(QWidget):
    """ChessBase-style game list + board: open file, paste, double-click to analyse."""

    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._games: tuple[PgnGame, ...] = ()
        self._current_index: int | None = None
        self._source_path: Path | None = None
        self._chrome_visible = True
        self._index: PositionIndex | None = None
        self._index_token: tuple[int, str] | None = None
        self._filter_hits: tuple[PositionHit, ...] | None = None
        self._indexing = False

        title = QLabel("Анализ партий")
        title.setObjectName("panelTitle")
        self.hint = QLabel(
            "Откройте PGN-базу или вставьте текст. В списке — метаданные одной строкой; "
            "двойной клик открывает партию на доске. "
            "«Найти позицию» показывает все партии, где встретилась позиция на доске, "
            "в том числе если ходы шли в другом порядке. "
            "Ctrl+Shift+B — спрятать/показать список и поле ввода (больше доски). "
            "Из архивной позиции можно начать временную ветку."
        )
        tighten_wrapping_label(self.hint)

        self.pgn_text = QPlainTextEdit()
        self.pgn_text.setPlaceholderText(
            "Вставьте PGN или откройте файл (.pgn / .txt), затем «Загрузить PGN»."
        )
        self.pgn_text.setMaximumHeight(120)

        self.open_button = QPushButton("Открыть файл…")
        self.paste_button = QPushButton("Вставить из буфера")
        self.load_button = QPushButton("Загрузить PGN")
        self.clear_button = QPushButton("Очистить")
        self.prev_button = QPushButton("←")
        self.prev_button.setToolTip("Предыдущая партия (Ctrl+←)")
        self.next_button = QPushButton("→")
        self.next_button.setToolTip("Следующая партия (Ctrl+→)")
        self.search_position_button = QPushButton("Найти позицию")
        self.search_position_button.setToolTip(
            "Партии базы, в которых встречалась позиция на доске, "
            "включая другой порядок ходов (Ctrl+F)"
        )
        self.search_position_button.setEnabled(False)
        self.show_all_button = QPushButton("Все партии")
        self.show_all_button.setToolTip("Снять фильтр позиции")
        self.show_all_button.setEnabled(False)
        self.focus_button = QPushButton("Больше доски")
        self.focus_button.setToolTip("Скрыть список и поле ввода (Ctrl+Shift+B)")
        self.focus_button.setCheckable(True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.open_button)
        toolbar.addWidget(self.paste_button)
        toolbar.addWidget(self.load_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addWidget(self.prev_button)
        toolbar.addWidget(self.next_button)
        toolbar.addWidget(self.search_position_button)
        toolbar.addWidget(self.show_all_button)
        toolbar.addWidget(self.focus_button)
        toolbar.addStretch()

        self.games_table = QTableWidget(0, len(_GAMES_COLUMNS))
        self.games_table.setObjectName("pgnAnalysisList")
        self.games_table.setHorizontalHeaderLabels(_GAMES_COLUMNS)
        self.games_table.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        header = self.games_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.games_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.games_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.games_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.games_table.setAlternatingRowColors(True)
        self.games_table.verticalHeader().setVisible(False)
        self.games_table.setMinimumHeight(100)
        self.games_table.setMaximumHeight(220)

        self.list_status = QLabel("Партии ещё не загружены.")
        tighten_wrapping_label(self.list_status)

        self._chrome = QWidget()
        chrome_layout = QVBoxLayout(self._chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.addWidget(self.hint)
        chrome_layout.addWidget(self.pgn_text)
        chrome_layout.addWidget(self.games_table)
        chrome_layout.addWidget(self.list_status)

        self.game = LocalGameWidget(
            mode_resolver,
            mode_id,
            allow_temporary_variations=True,
            analysis_mode=True,
        )
        self.game.new_game_button.hide()
        self.game.quit_button.hide()
        self.game.instructions.setText(
            "Клик по записи открывает позицию. ←/→ в списке ходов — полуходы; "
            "Ctrl+←/→ — соседняя партия в файле. "
            "Двойной клик по строке списка открывает партию. "
            "Ctrl+Shift+B — больше места под доску."
        )

        self._split = QSplitter(Qt.Orientation.Vertical)
        self._split.addWidget(self._chrome)
        self._split.addWidget(self.game)
        self._split.setStretchFactor(0, 0)
        self._split.setStretchFactor(1, 1)
        self._split.setSizes((280, 520))

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._split, 1)

        self.open_button.clicked.connect(self._open_file)
        self.paste_button.clicked.connect(self._paste_clipboard)
        self.load_button.clicked.connect(lambda: self.load_pgn())
        self.clear_button.clicked.connect(self._clear)
        self.prev_button.clicked.connect(self.open_previous_game)
        self.next_button.clicked.connect(self.open_next_game)
        self.search_position_button.clicked.connect(lambda: self.search_position())
        self.show_all_button.clicked.connect(self.clear_position_filter)
        self.focus_button.toggled.connect(self._on_focus_toggled)
        self.games_table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.game.board.square_clicked.connect(self._on_board_clicked)

        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        self._focus_shortcut.activated.connect(self.toggle_chrome)
        self._prev_shortcut = QShortcut(QKeySequence("Ctrl+Left"), self)
        self._prev_shortcut.activated.connect(self.open_previous_game)
        self._next_shortcut = QShortcut(QKeySequence("Ctrl+Right"), self)
        self._next_shortcut.activated.connect(self.open_next_game)
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self.search_position)

        self._sync_nav_buttons()

    @property
    def games(self) -> tuple[PgnGame, ...]:
        return self._games

    @property
    def current_index(self) -> int | None:
        return self._current_index

    def set_mode(self, mode_id: str) -> None:
        self._drop_index()
        had_filter = self._filter_hits is not None
        self._filter_hits = None
        self.show_all_button.setEnabled(False)
        self.game.set_mode(mode_id)
        if had_filter and self._games:
            self._fill_games_table()

    def reload_piece_assets(self) -> None:
        self.game.reload_piece_assets()

    def load_position(self, state: GameState) -> None:
        self.game.load_position(state)
        self._current_index = None
        self.games_table.clearSelection()
        self._sync_nav_buttons()
        self.list_status.setText(
            "Позиция из редактора. Ходите фигурами; G — оценка, H — подсказка движка."
        )
        self.set_chrome_visible(False)
        self.game.status.setText(
            "Анализ позиции из редактора. Клик по фигуре и клетке — ход; "
            "Ctrl+Z — отмена; из архива можно начать временную ветку."
        )

    def toggle_chrome(self) -> None:
        self.set_chrome_visible(not self._chrome_visible)

    def set_chrome_visible(self, visible: bool) -> None:
        self._chrome_visible = visible
        self._chrome.setVisible(visible)
        self.focus_button.blockSignals(True)
        self.focus_button.setChecked(not visible)
        self.focus_button.blockSignals(False)
        self.focus_button.setText("Показать список" if not visible else "Больше доски")
        if visible:
            self._split.setSizes((280, 520))
        else:
            self._split.setSizes((0, 800))

    def load_pgn(self, text: str | None = None) -> bool:
        payload = (text if text is not None else self.pgn_text.toPlainText()).strip()
        if not payload:
            QMessageBox.warning(self, "PGN не загружен", "Вставьте или откройте PGN.")
            return False
        if not looks_like_pgn(payload):
            QMessageBox.warning(
                self,
                "Не похоже на PGN",
                "Текст не содержит тегов [Event] или нумерации ходов (1.).",
            )
            return False
        try:
            games = parse_pgn(payload)
        except ValueError as error:
            QMessageBox.critical(self, "Не удалось разобрать PGN", str(error))
            return False
        if not games:
            QMessageBox.warning(self, "PGN пуст", "В тексте нет партий.")
            return False
        self.pgn_text.setPlainText(payload)
        self._games = games
        self._drop_index()
        self._filter_hits = None
        self.search_position_button.setEnabled(True)
        self.show_all_button.setEnabled(False)
        self._fill_games_table()
        self._current_index = None
        opened = self.open_game_at(0)
        if opened:
            self.list_status.setText(
                f"Загружено партий: {len(games)}. "
                "«Найти позицию» — где встретилась позиция на доске, включая перестановки. "
                "Двойной клик — открыть; Ctrl+←/→ — соседи."
            )
        return opened

    def search_position(self, state: GameState | None = None) -> int:
        """Filter the loaded database to games that reached the board position.

        Move order does not matter: a transposition is the same position.
        Returns how many games matched.
        """
        if self._indexing:
            return 0
        if not self._games:
            self.list_status.setText("Сначала загрузите базу партий.")
            return 0
        self._indexing = True
        try:
            query = self.game.service.state if state is None else state
            mode = self.game.service.mode
            if self._index is None or self._index_token != (id(self._games), mode.id):
                self.list_status.setText("Строю указатель позиций…")
                QApplication.processEvents()
            index = self._ensure_index()
            hits = index.find(query)
            self._filter_hits = hits
            self.show_all_button.setEnabled(True)
            self._fill_games_table()
            self.set_chrome_visible(True)
            if not hits:
                self.list_status.setText(
                    f"Такой позиции в базе нет (партий: {len(self._games)}, "
                    f"уникальных позиций: {index.position_count})."
                )
                self._sync_nav_buttons()
                return 0
            self.list_status.setText(
                f"Найдено партий: {len(hits)} из {len(self._games)}. "
                "Одинаковая позиция находится и при другом порядке ходов. "
                "Двойной клик открывает её в партии."
            )
            chosen = next(
                (hit for hit in hits if hit.game_index == self._current_index),
                hits[0],
            )
            self.open_game_at(
                chosen.game_index,
                ply=chosen.ply if chosen.on_mainline else None,
                on_mainline=chosen.on_mainline,
            )
            return len(hits)
        finally:
            self._indexing = False

    def clear_position_filter(self) -> None:
        """Show every loaded game again. The board stays where it is."""
        self._filter_hits = None
        self.show_all_button.setEnabled(False)
        self._fill_games_table()
        if self._games:
            self.list_status.setText(f"Показаны все партии: {len(self._games)}.")
        if self._current_index is not None:
            row = self._row_of(self._current_index)
            if row is not None:
                self.games_table.selectRow(row)
        self._sync_nav_buttons()

    def open_game_at(
        self,
        index: int,
        *,
        ply: int | None = None,
        on_mainline: bool = True,
    ) -> bool:
        if not self._games or not 0 <= index < len(self._games):
            return False
        game = self._games[index]
        try:
            self.game.load_pgn_game(game)
        except (RuntimeError, ValueError) as error:
            QMessageBox.critical(
                self,
                "Не удалось загрузить партию",
                f"{error}\n\nПроверьте, что слева выбран правильный режим игры.",
            )
            return False
        if on_mainline and ply is not None:
            self.game.show_revision(ply)
        self._current_index = index
        row = self._row_of(index)
        if row is not None:
            self.games_table.selectRow(row)
            item = self.games_table.item(row, 0)
            if item is not None:
                self.games_table.scrollToItem(item)
        self._sync_nav_buttons()
        if on_mainline and ply == 0:
            note = " Показана начальная позиция."
        elif on_mainline and ply is not None:
            note = f" Показана позиция после {ply}-го полухода."
        elif not on_mainline:
            note = " Эта позиция встретилась в варианте; на доске основная партия."
        else:
            note = " Выберите ход в записи для просмотра."
        self.game.status.setText(
            f"Партия {index + 1}/{len(self._games)}: {game.white} — {game.black} "
            f"({game.result}).{note}"
        )
        return True

    def open_previous_game(self) -> bool:
        return self._open_neighbor(-1)

    def open_next_game(self) -> bool:
        return self._open_neighbor(1)

    def _open_neighbor(self, step: int) -> bool:
        visible = self._visible_game_indices()
        if self._current_index not in visible:
            return False
        position = visible.index(self._current_index) + step
        if not 0 <= position < len(visible):
            return False
        game_index = visible[position]
        hit = self._hit_for(game_index)
        if hit is None:
            return self.open_game_at(game_index)
        return self.open_game_at(
            game_index,
            ply=hit.ply if hit.on_mainline else None,
            on_mainline=hit.on_mainline,
        )

    def _fill_games_table(self) -> None:
        if self._filter_hits is None:
            rows = tuple(
                (game_index, game, None, True)
                for game_index, game in enumerate(self._games)
            )
        else:
            rows = tuple(
                (
                    hit.game_index,
                    self._games[hit.game_index],
                    hit.ply if hit.on_mainline else None,
                    hit.on_mainline,
                )
                for hit in self._filter_hits
            )
        self.games_table.setRowCount(len(rows))
        for row, (game_index, game, ply, on_mainline) in enumerate(rows):
            values = (
                str(game_index + 1),
                game.white,
                game.black,
                game.result,
                game.date,
                game.tag("Round", ""),
                game.tag("ECO", ""),
                game.event,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(
                        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    )
                    item.setData(Qt.ItemDataRole.UserRole, game_index)
                    if ply is not None:
                        item.setData(Qt.ItemDataRole.UserRole + 1, ply)
                    item.setData(Qt.ItemDataRole.UserRole + 2, 1 if on_mainline else 0)
                self.games_table.setItem(row, column, item)

    def _sync_nav_buttons(self) -> None:
        visible = self._visible_game_indices()
        index = self._current_index
        position = visible.index(index) if index in visible else None
        self.prev_button.setEnabled(position is not None and position > 0)
        self.next_button.setEnabled(
            position is not None and position < len(visible) - 1
        )

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        item = self.games_table.item(row, 0)
        game_index = row
        ply: int | None = None
        on_mainline = True
        if item is not None:
            stored = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(stored, int) and not isinstance(stored, bool):
                game_index = stored
            stored_ply = item.data(Qt.ItemDataRole.UserRole + 1)
            if isinstance(stored_ply, int) and not isinstance(stored_ply, bool):
                ply = stored_ply
            stored_line = item.data(Qt.ItemDataRole.UserRole + 2)
            if stored_line == 0:
                on_mainline = False
        self.open_game_at(game_index, ply=ply, on_mainline=on_mainline)

    def _on_focus_toggled(self, checked: bool) -> None:
        self.set_chrome_visible(not checked)

    def _on_board_clicked(self, _index: int) -> None:
        if self._chrome_visible and not self._games:
            self.set_chrome_visible(False)

    def _open_file(self) -> None:
        start = ""
        if self._source_path is not None:
            start = str(self._source_path.parent)
        chosen, _filter = QFileDialog.getOpenFileName(
            self,
            "Открыть PGN",
            start,
            "PGN / текст (*.pgn *.txt);;Все файлы (*.*)",
        )
        if not chosen:
            return
        path = Path(chosen)
        try:
            text = read_pgn_text(path)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось прочитать файл", str(exc))
            return
        self._source_path = path
        self.pgn_text.setPlainText(text)
        self.load_pgn(text)

    def _paste_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text().strip()
        if not text:
            QMessageBox.information(self, "Буфер пуст", "Скопируйте PGN в буфер обмена.")
            return
        self._source_path = None
        self.pgn_text.setPlainText(text)
        self.load_pgn(text)

    def _clear(self) -> None:
        self.pgn_text.clear()
        self._games = ()
        self._current_index = None
        self._source_path = None
        self._drop_index()
        self._filter_hits = None
        self.search_position_button.setEnabled(False)
        self.show_all_button.setEnabled(False)
        self.games_table.setRowCount(0)
        self.list_status.setText("Партии ещё не загружены.")
        self._sync_nav_buttons()
        self.game.reset_game()
        self.set_chrome_visible(True)

    def _ensure_index(self) -> PositionIndex:
        mode = self.game.service.mode
        token = (id(self._games), mode.id)
        if self._index is None or self._index_token != token:
            self._index = build_position_index(self._games, mode)
            self._index_token = token
        return self._index

    def _drop_index(self) -> None:
        self._index = None
        self._index_token = None

    def _visible_game_indices(self) -> tuple[int, ...]:
        if self._filter_hits is None:
            return tuple(range(len(self._games)))
        return tuple(hit.game_index for hit in self._filter_hits)

    def _hit_for(self, game_index: int) -> PositionHit | None:
        if self._filter_hits is None:
            return None
        for hit in self._filter_hits:
            if hit.game_index == game_index:
                return hit
        return None

    def _row_of(self, game_index: int) -> int | None:
        for row in range(self.games_table.rowCount()):
            item = self.games_table.item(row, 0)
            if item is None:
                continue
            stored = item.data(Qt.ItemDataRole.UserRole)
            if stored == game_index:
                return row
        return None
