"""Tournament manager page: modern Swiss Manager-style workspace."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QModelIndex, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence, QMouseEvent, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.tournament.excel_export import export_tournament_xlsx
from chess_core.app.tournament.manager import TournamentManager
from chess_core.app.tournament.models import (
    RESULT_BLACK,
    RESULT_DOUBLE_FORFEIT,
    RESULT_DRAW,
    RESULT_FORFEIT_BLACK,
    RESULT_FORFEIT_WHITE,
    RESULT_HPB,
    RESULT_WHITE,
    PairingSystem,
    Player,
    PlayerStatus,
    parse_player_list,
)
from chess_core.app.tournament.player_import import (
    import_players_from_excel,
    import_players_from_google_sheet,
    import_players_from_xlsx,
    parse_players_csv,
)
from chess_core.app.tournament.state import TournamentSettings, new_tournament_state
from chess_core.infra.storage.tournament_files import load_tournament, save_tournament, save_trf
from chess_core.ui.theme import tighten_wrapping_label
from chess_core.ui.widgets.tournament.pairing_edit import PairingEditDialog
from chess_core.ui.widgets.tournament.result_combo import ResultCombo
from chess_core.ui.widgets.tournament.player_dialog import (
    GoogleSheetDialog,
    PlayerDialog,
    TournamentPropertiesDialog,
)

_SYSTEM_LABELS = (
    (PairingSystem.SWISS, "Швейцарская (FIDE Dutch 2026)"),
    (PairingSystem.SWISS_NO_COLOR, "Швейцарская (без цвета)"),
    (PairingSystem.ROUND_ROBIN, "Круговая (Бергер)"),
    (PairingSystem.KNOCKOUT, "Олимпийская"),
    (PairingSystem.SCHEVENINGEN, "Шевенинген"),
    (PairingSystem.COLOR_DRAW, "Жеребьёвка цвета"),
)

_RESULT_OPTIONS = (
    ("", "—"),
    (RESULT_WHITE, "1-0"),
    (RESULT_DRAW, "½"),
    (RESULT_BLACK, "0-1"),
    (RESULT_FORFEIT_WHITE, "+/−"),
    (RESULT_FORFEIT_BLACK, "−/+"),
    (RESULT_DOUBLE_FORFEIT, "0-0"),
)

_STATUS_LABELS = {
    PlayerStatus.ACTIVE: "играет",
    PlayerStatus.ABSENT: "неявка",
    PlayerStatus.WITHDRAWN: "снят",
    PlayerStatus.LATE_ENTRY: "дозаявка",
}

_USER_ROLE = int(Qt.ItemDataRole.UserRole)
_DRAFT_ROLE = _USER_ROLE + 1
_DRAFT_EDITABLE = (1, 2, 3, 4, 5)


class TournamentWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = TournamentManager()
        self._path: Path | None = None
        self._view_round = 1
        self._syncing = False
        self._player_draft = False
        self._stop_player_chain = False

        self.name_edit = QLineEdit("Tournament")
        self.name_edit.setPlaceholderText("Название турнира")
        self.system = QComboBox()
        for system, label in _SYSTEM_LABELS:
            self.system.addItem(label, system)
        self.rounds = QSpinBox()
        self.rounds.setRange(1, 32)
        self.rounds.setValue(5)
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 2)
        self.cycles.setValue(1)
        self.seed = QSpinBox()
        self.seed.setRange(0, 1_000_000)
        self.seed.setValue(1)
        self.close_list = QCheckBox("Список закрыт")
        self.status = QLabel(
            "Добавьте игроков и откройте вкладку «Пары». Движок не сертифицирован FIDE."
        )
        self.status.setObjectName("gameStatus")
        tighten_wrapping_label(self.status)

        self.open_button = QPushButton("Открыть")
        self.save_button = QPushButton("Сохранить")
        self.export_button = QPushButton("Excel")
        self.trf_button = QPushButton("TRF")
        self.properties_button = QPushButton("Свойства")
        self.reset = QPushButton("Сброс")
        self.generate = QPushButton("Следующий тур")
        self.edit_pairs_button = QPushButton("Изменить пары")
        self.invert_button = QPushButton("Цвета")
        self.copy_button = QPushButton("Копировать пары")
        self.delete_round_button = QPushButton("Удалить тур")
        self.add_player_button = QPushButton("Добавить")
        self.edit_player_button = QPushButton("Изменить")
        self.sort_rating_button = QPushButton("По рейтингу")
        self.import_csv_button = QPushButton("CSV")
        self.import_xlsx_button = QPushButton("XLS/XLSX")
        self.import_google_button = QPushButton("Google")
        self.absent_button = QPushButton("Неявка")
        self.withdraw_button = QPushButton("Снять")
        self.restore_button = QPushButton("Вернуть")
        self.bye_button = QPushButton("½ bye")
        self.round_spin = QSpinBox()
        self.round_spin.setRange(1, 1)
        self.round_spin.setValue(1)
        self.round_spin.setPrefix("Тур ")

        self.players_edit = QPlainTextEdit()
        self.players_edit.setPlaceholderText(
            "Или вставьте список: Имя|рейтинг|команда — по одному игроку на строку."
        )
        self.players_edit.setMaximumHeight(110)
        self.players_table = QTableWidget(0, 8)
        self.players_table.setHorizontalHeaderLabels(
            ("Ст. №", "Зв.", "Игрок", "Фед.", "Рейтинг", "Клуб", "Очки", "Статус")
        )
        self.pairings = QTableWidget(0, 5)
        self.pairings.setHorizontalHeaderLabels(("Доска", "Белые", "Чёрные", "Результат", "Примечание"))
        self.standings = QTableWidget(0, 11)
        self.standings.setHorizontalHeaderLabels(
            ("Место", "Ст. №", "Зв.", "Игрок", "Рейтинг", "Очки", "Партии", "+/=/−", "Бухгольц", "Бергер", "б/ч")
        )
        self.crosstable = QTableWidget(0, 4)
        self.audit = QTableWidget(0, 5)
        self.audit.setHorizontalHeaderLabels(("Действие", "Причина", "Тур", "Деталь", "Замечания"))
        for table in (
            self.players_table,
            self.pairings,
            self.standings,
            self.crosstable,
            self.audit,
        ):
            table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.setAlternatingRowColors(True)
        self.players_table.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._players_page(), "Игроки")
        self.tabs.addTab(self._pairings_page(), "Пары")
        self.tabs.addTab(self._wrap(self.standings), "Таблица")
        self.tabs.addTab(self._wrap(self.crosstable), "Кросс-таблица")
        self.tabs.addTab(self._wrap(self.audit), "Журнал")

        layout = QVBoxLayout(self)
        layout.addLayout(self._toolbar())
        layout.addLayout(self._settings_row())
        layout.addWidget(self.status)
        layout.addWidget(self.tabs, 1)

        self.open_button.clicked.connect(self._open_dialog)
        self.save_button.clicked.connect(self._save_dialog)
        self.export_button.clicked.connect(self._export_dialog)
        self.trf_button.clicked.connect(self._export_trf_dialog)
        self.properties_button.clicked.connect(self._properties_dialog)
        self.reset.clicked.connect(self._reset)
        self.generate.clicked.connect(self._next_round)
        self.edit_pairs_button.clicked.connect(self._edit_pairs_dialog)
        self.invert_button.clicked.connect(self._invert_selected)
        self.copy_button.clicked.connect(self._copy_pairings)
        self.delete_round_button.clicked.connect(self._delete_round_dialog)
        self.add_player_button.clicked.connect(self._begin_player_entry)
        self.edit_player_button.clicked.connect(self._edit_player_dialog)
        self.sort_rating_button.clicked.connect(self._sort_starting_list)
        self.import_csv_button.clicked.connect(self._import_csv_dialog)
        self.import_xlsx_button.clicked.connect(self._import_xlsx_dialog)
        self.import_google_button.clicked.connect(self._import_google_dialog)
        self.absent_button.clicked.connect(lambda: self._set_selected_status(PlayerStatus.ABSENT))
        self.withdraw_button.clicked.connect(lambda: self._set_selected_status(PlayerStatus.WITHDRAWN))
        self.restore_button.clicked.connect(lambda: self._set_selected_status(PlayerStatus.ACTIVE))
        self.bye_button.clicked.connect(self._schedule_half_bye)
        self.system.currentIndexChanged.connect(self._on_system_changed)
        self.round_spin.valueChanged.connect(self._on_round_changed)
        self.name_edit.editingFinished.connect(self._apply_header_settings)
        self.close_list.toggled.connect(self._apply_header_settings)
        self.players_table.cellDoubleClicked.connect(self._on_player_double_clicked)
        self.players_table.cellChanged.connect(self._on_player_cell_changed)
        self.players_table.installEventFilter(self)
        self.players_table.viewport().installEventFilter(self)
        QShortcut(QKeySequence.StandardKey.Save, self).activated.connect(self._save_dialog)
        QShortcut(QKeySequence.StandardKey.Open, self).activated.connect(self._open_dialog)
        self._on_system_changed()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 — Qt API
        players_page = getattr(self, "_players_page_widget", None)
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            if watched in {self.players_table, self.players_table.viewport()} and self._player_draft:
                self._discard_player_draft()
                self._clear_player_selection()
                return True
        if isinstance(event, QMouseEvent):
            pos = event.position().toPoint()
            if watched is self.players_table.viewport():
                index = self.players_table.indexAt(pos)
                if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                    if index.isValid() and self._edit_player_at_row(index.row()):
                        return True
                if event.type() == QEvent.Type.MouseButtonPress:
                    if not index.isValid():
                        if event.button() == Qt.MouseButton.LeftButton:
                            self._stop_player_chain = True
                            self._close_player_editor()
                            self._clear_player_selection()
                        elif event.button() == Qt.MouseButton.MiddleButton:
                            self._begin_player_entry()
                            return True
            elif (
                watched is players_page
                and event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.MiddleButton
            ):
                child = players_page.childAt(pos)
                if child is None or child is players_page:
                    self._begin_player_entry()
                    return True
        return super().eventFilter(watched, event)

    def _clear_player_selection(self) -> None:
        if self._player_draft and not self._draft_has_name():
            self._discard_player_draft()
        self.players_table.clearSelection()
        self.players_table.setCurrentIndex(QModelIndex())
        self._stop_player_chain = False

    def _draft_row(self) -> int | None:
        if not self._player_draft:
            return None
        for row in range(self.players_table.rowCount()):
            item = self.players_table.item(row, 2)
            if item is not None and item.data(_DRAFT_ROLE):
                return row
        return None

    def _draft_has_name(self) -> bool:
        row = self._draft_row()
        if row is None:
            return False
        item = self.players_table.item(row, 2)
        return bool(item is not None and item.text().strip())

    def _begin_player_entry(self) -> None:
        if self._manager.state.settings.list_closed and self._manager.current_round == 0:
            self.status.setText("Список закрыт.")
            return
        if self._player_draft:
            self._focus_draft_name()
            return
        try:
            self._ensure_seed_manager()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self._stop_player_chain = False
        self._player_draft = True
        self._append_draft_row()
        self._focus_draft_name()
        self.status.setText("Введите имя. Enter — следующий игрок, клик по пустому месту — закончить.")

    def _append_draft_row(self) -> None:
        row = self.players_table.rowCount()
        self.players_table.blockSignals(True)
        try:
            self.players_table.insertRow(row)
            values = ("", "", "", "", "", "", "", "черновик")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in _DRAFT_EDITABLE:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 2:
                    item.setData(_DRAFT_ROLE, True)
                self.players_table.setItem(row, column, item)
        finally:
            self.players_table.blockSignals(False)

    def _focus_draft_name(self) -> None:
        row = self._draft_row()
        if row is None:
            return
        self.players_table.setCurrentCell(row, 2)
        item = self.players_table.item(row, 2)
        if item is not None:
            self.players_table.editItem(item)

    def _close_player_editor(self) -> None:
        editor = QApplication.focusWidget()
        if editor is None or editor is self.players_table:
            return
        if editor is self.players_table.viewport() or not self.players_table.isAncestorOf(editor):
            return
        self.players_table.commitData(editor)
        self.players_table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.SubmitModelCache)

    def _read_draft_values(self) -> dict | None:
        row = self._draft_row()
        if row is None:
            return None

        def text(column: int) -> str:
            item = self.players_table.item(row, column)
            return (item.text() if item else "").strip()

        name = text(2)
        if not name:
            return None
        rating_text = text(4)
        try:
            rating = int(rating_text) if rating_text else 0
        except ValueError:
            rating = 0
        return {
            "name": name,
            "rating": rating,
            "title": text(1),
            "federation": text(3),
            "team": text(5) or None,
        }

    def _commit_player_draft(self, *, chain: bool) -> bool:
        values = self._read_draft_values()
        if values is None:
            return False
        self._player_draft = False
        try:
            self._ensure_seed_manager()
            self._manager.add_player(**values)
        except ValueError as exc:
            self.status.setText(str(exc))
            self._player_draft = True
            return False
        self._refresh()
        if chain:
            self._begin_player_entry()
        else:
            self.status.setText(f"Добавлен игрок: {values['name']}.")
        return True

    def _discard_player_draft(self) -> None:
        row = self._draft_row()
        self._player_draft = False
        if row is None:
            return
        self.players_table.blockSignals(True)
        try:
            self.players_table.removeRow(row)
        finally:
            self.players_table.blockSignals(False)
        self.status.setText("Черновик игрока удалён.")

    def _on_player_cell_changed(self, row: int, column: int) -> None:
        if self._syncing or not self._player_draft:
            return
        if column != 2 or row != self._draft_row():
            return
        if not self._draft_has_name():
            return
        self._commit_player_draft(chain=not self._stop_player_chain)

    def _toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel("Турнир")
        title.setObjectName("panelTitle")
        row.addWidget(title)
        row.addWidget(self.name_edit, 1)
        row.addWidget(self.open_button)
        row.addWidget(self.save_button)
        row.addWidget(self.export_button)
        row.addWidget(self.trf_button)
        row.addWidget(self.properties_button)
        row.addWidget(self.reset)
        return row

    def _settings_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for label, widget in (
            ("Система", self.system),
            ("Туры", self.rounds),
            ("Круги", self.cycles),
        ):
            caption = QLabel(label)
            caption.setObjectName("panelTitle")
            row.addWidget(caption)
            row.addWidget(widget)
        row.addWidget(self.close_list)
        row.addStretch()
        return row

    def _players_page(self) -> QWidget:
        page = QWidget()
        self._players_page_widget = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        buttons = QHBoxLayout()
        for widget in (
            self.add_player_button,
            self.edit_player_button,
            self.sort_rating_button,
            self.import_csv_button,
            self.import_xlsx_button,
            self.import_google_button,
            self.absent_button,
            self.withdraw_button,
            self.restore_button,
            self.bye_button,
        ):
            buttons.addWidget(widget)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addWidget(self.players_table, 1)
        hint = QLabel(
            "Перед 1-м туром стартовый список сортируется по рейтингу, затем званию и имени. "
            "Колёсико мыши — новый игрок; после имени сразу появится следующий. "
            "Клик по пустому месту без имени удаляет черновик и заканчивает ввод."
        )
        hint.setObjectName("gameHint")
        tighten_wrapping_label(hint)
        layout.addWidget(hint)
        layout.addWidget(self.players_edit)
        page.installEventFilter(self)
        return page

    def _pairings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        buttons = QHBoxLayout()
        buttons.addWidget(self.round_spin)
        buttons.addWidget(self.generate)
        buttons.addWidget(self.edit_pairs_button)
        buttons.addWidget(self.invert_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.delete_round_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addWidget(self.pairings, 1)
        hint = QLabel("↑↓ — следующая пара, ←→ — результат, 1 / 2 / 0 — 1-0 / ничья / 0-1, + / − — неявка.")
        hint.setObjectName("gameHint")
        tighten_wrapping_label(hint)
        layout.addWidget(hint)
        return page

    def _wrap(self, table: QTableWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(table)
        return page

    @property
    def _service(self) -> TournamentManager:
        return self._manager

    def import_csv_text(self, text: str) -> None:
        report = parse_players_csv(text)
        self._apply_import(report.players, report.errors, report.duplicates)

    def import_google_url(self, url: str, *, opener=None) -> None:
        report = import_players_from_google_sheet(url, opener=opener)
        self._apply_import(report.players, report.errors, report.duplicates)

    def save_to(self, path: str | Path) -> Path:
        self._ensure_manager_from_text()
        self._apply_header_settings()
        saved = save_tournament(self._manager.state, path)
        self._path = saved
        self.status.setText(f"Сохранено: {saved}")
        return saved

    def load_from(self, path: str | Path) -> None:
        state = load_tournament(path)
        self._manager = TournamentManager(state)
        opened = Path(path)
        self._path = opened if opened.suffix.lower() in {".json"} else None
        self._view_round = max(1, state.current_round)
        self._sync_controls_from_state()
        self._refresh()
        self.status.setText(_open_status(opened, state.settings.name))

    def export_xlsx_to(self, path: str | Path) -> Path:
        self._ensure_manager_from_text()
        return export_tournament_xlsx(self._manager.state, path)

    def _apply_import(self, players, errors, duplicates) -> None:
        if players:
            try:
                if self._manager.state.current_round == 0 and not self._manager.players:
                    self._manager = TournamentManager.create(players, self._settings_from_controls())
                else:
                    self._manager.add_players(players)
            except ValueError as exc:
                self.status.setText(str(exc))
                return
            self._sync_players_edit()
        message = f"Импортировано игроков: {len(players)}."
        if duplicates:
            message += " Дубликаты: " + ", ".join(duplicates)
        if errors:
            message += " Ошибки: " + "; ".join(errors)
        self.status.setText(message)
        self._refresh()

    def _settings_from_controls(self) -> TournamentSettings:
        system = self.system.currentData()
        if not isinstance(system, PairingSystem):
            system = PairingSystem.SWISS
        current = self._manager.state.settings
        return TournamentSettings(
            name=self.name_edit.text().strip() or "Tournament",
            system=system,
            declared_rounds=self.rounds.value(),
            rr_cycles=self.cycles.value(),
            seed=self.seed.value(),
            list_closed=self.close_list.isChecked(),
            site=current.site,
            arbiter=current.arbiter,
            time_control=current.time_control,
            initial_color=current.initial_color,
            pairing_engine=current.pairing_engine,
        )

    def _apply_header_settings(self) -> None:
        if self._syncing:
            return
        self._manager.update_settings(self._settings_from_controls())
        self._lock_started_controls()

    def _ensure_manager_from_text(self) -> None:
        if self._manager.players:
            self._apply_header_settings()
            return
        players = parse_player_list(self.players_edit.toPlainText())
        if len(players) < 2:
            raise ValueError("tournament needs at least two players")
        self._manager = TournamentManager.create(players, self._settings_from_controls())

    def _reset(self, *_args) -> None:
        if self._manager.players or self._manager.pairings:
            answer = QMessageBox.question(
                self,
                "Сброс",
                "Сбросить турнир и список игроков?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._manager = TournamentManager()
        self._path = None
        self._view_round = 1
        self.players_edit.clear()
        self.name_edit.setText("Tournament")
        self.close_list.setChecked(False)
        self._refresh()
        self.status.setText("Добавьте игроков и откройте вкладку «Пары». Движок не сертифицирован FIDE.")

    def _next_round(self) -> None:
        try:
            self._ensure_manager_from_text()
            self._manager.generate_next_round()
            extra = ""
            if self._manager.last_engine_report:
                extra = " " + "; ".join(self._manager.last_engine_report)
            self._view_round = self._manager.current_round
            self.status.setText(f"Сгенерирован тур {self._manager.current_round}.{extra}")
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))
            return
        self._refresh()
        self.tabs.setCurrentIndex(1)
        self._focus_result_combo(0)

    def _refresh(self) -> None:
        self._syncing = True
        try:
            self._lock_started_controls()
            self._refresh_players()
            self._refresh_pairings()
            self._refresh_standings()
            self._refresh_crosstable()
            self._refresh_audit()
        finally:
            self._syncing = False

    def _lock_started_controls(self) -> None:
        started = self._manager.current_round > 0
        self.system.setEnabled(not started)
        self.rounds.setEnabled(not started)
        self.cycles.setEnabled(not started and self.system.currentData() is PairingSystem.ROUND_ROBIN)
        closed = self._manager.state.settings.list_closed and not started
        self.add_player_button.setEnabled(not closed)
        self.import_csv_button.setEnabled(not closed)
        self.import_xlsx_button.setEnabled(not closed)
        self.import_google_button.setEnabled(not closed)
        self.delete_round_button.setEnabled(self._manager.current_round > 0)
        self.sort_rating_button.setEnabled(self._manager.can_sort_starting_list())

    def _refresh_players(self) -> None:
        points = {row.player.player_id: row.points for row in self._manager.standings()}
        scheduled = dict(self._manager.state.scheduled_byes)
        players = self._manager.starting_list()
        self.players_table.blockSignals(True)
        self.players_table.setRowCount(len(players))
        for row, player in enumerate(players):
            status = _STATUS_LABELS.get(player.status, player.status.value)
            if player.player_id in scheduled:
                status += f" · {scheduled[player.player_id]}"
            values = (
                str(player.start_number or ""),
                player.title,
                player.name,
                player.federation,
                str(player.rating),
                player.team or "",
                str(points.get(player.player_id, 0.0)),
                status,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 2:
                    item.setData(_USER_ROLE, player.player_id)
                self.players_table.setItem(row, column, item)
        self.players_table.blockSignals(False)
        if self._player_draft:
            self._append_draft_row()
        self._sync_players_edit()

    def _refresh_pairings(self) -> None:
        current = max(self._manager.current_round, 1)
        self.round_spin.blockSignals(True)
        self.round_spin.setRange(1, current)
        self.round_spin.setValue(min(max(1, self._view_round), current))
        self.round_spin.blockSignals(False)
        self._view_round = self.round_spin.value()
        names = self._manager.state.player_map()
        shown = self._manager.round_pairings(self._view_round)
        self.pairings.setRowCount(len(shown))
        for row, pairing in enumerate(shown):
            white = names.get(pairing.white_id or "")
            black = names.get(pairing.black_id or "")
            note = []
            if pairing.manual:
                note.append("вручную")
            if pairing.is_bye:
                note.append(pairing.result or "bye")
            self.pairings.setItem(row, 0, QTableWidgetItem(str(pairing.board)))
            self.pairings.setItem(row, 1, QTableWidgetItem(_board_name(white)))
            self.pairings.setItem(row, 2, QTableWidgetItem(_board_name(black)))
            self.pairings.setItem(row, 4, QTableWidgetItem(" · ".join(note)))
            if pairing.is_bye:
                label = QLabel(pairing.result or "bye")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pairings.setCellWidget(row, 3, label)
            else:
                combo = ResultCombo()
                combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                for value, text in _RESULT_OPTIONS:
                    combo.addItem(text, value)
                index = combo.findData(pairing.result or "")
                combo.setCurrentIndex(max(0, index))
                combo.currentIndexChanged.connect(
                    self._make_result_handler(pairing.round_index, pairing.board, combo)
                )
                combo.navigate.connect(self._on_result_navigate)
                combo.advance.connect(lambda: self._on_result_navigate(1))
                self.pairings.setCellWidget(row, 3, combo)

    def _refresh_standings(self) -> None:
        table = self._manager.standings()
        self.standings.setRowCount(len(table))
        for row, standing in enumerate(table):
            player = standing.player
            values = (
                str(standing.place or row + 1),
                str(player.start_number or ""),
                player.title,
                player.name,
                str(player.rating),
                str(standing.points),
                str(standing.games),
                f"{standing.wins}/{standing.draws}/{standing.losses}",
                str(standing.buchholz),
                str(standing.sonneborn_berger),
                f"{standing.white_games}/{standing.black_games}",
            )
            for column, value in enumerate(values):
                self.standings.setItem(row, column, QTableWidgetItem(value))

    def _refresh_crosstable(self) -> None:
        rows = self._manager.crosstable()
        rounds = sorted({pairing.round_index for pairing in self._manager.pairings})
        headers = ["Место", "Ст. №", "Игрок", "Рейтинг"] + [str(item) for item in rounds] + ["Очки"]
        self.crosstable.setColumnCount(len(headers))
        self.crosstable.setHorizontalHeaderLabels(headers)
        self.crosstable.setRowCount(len(rows))
        for row, (standing, cells) in enumerate(rows):
            values = [
                str(standing.place or row + 1),
                str(standing.player.start_number or ""),
                standing.player.name,
                str(standing.player.rating),
            ]
            values.extend("" if cell is None else cell.label for cell in cells)
            values.append(str(standing.points))
            for column, value in enumerate(values):
                self.crosstable.setItem(row, column, QTableWidgetItem(value))

    def _refresh_audit(self) -> None:
        entries = self._manager.state.audit
        self.audit.setRowCount(len(entries))
        for row, entry in enumerate(reversed(entries)):
            values = (
                entry.action,
                entry.reason,
                "" if entry.round_index is None else str(entry.round_index),
                entry.detail,
                "; ".join(entry.warnings),
            )
            for column, value in enumerate(values):
                self.audit.setItem(row, column, QTableWidgetItem(value))

    def _make_result_handler(self, round_index: int, board: int, combo: QComboBox):
        def _set(_index: int = 0) -> None:
            if self._syncing:
                return
            result = combo.currentData()
            if not result:
                return
            try:
                self._manager.set_result(round_index, board, str(result))
                self.status.setText(f"Тур {round_index}, доска {board}: {result}")
                self._refresh_after_result()
            except (ValueError, KeyError) as exc:
                self.status.setText(str(exc))

        return _set

    def _refresh_after_result(self) -> None:
        self._syncing = True
        try:
            self._refresh_players()
            self._refresh_standings()
            self._refresh_crosstable()
            self._refresh_audit()
        finally:
            self._syncing = False

    def _result_combos(self) -> list[ResultCombo]:
        combos: list[ResultCombo] = []
        for row in range(self.pairings.rowCount()):
            widget = self.pairings.cellWidget(row, 3)
            if isinstance(widget, ResultCombo):
                combos.append(widget)
        return combos

    def _on_result_navigate(self, delta: int = 1) -> None:
        combos = self._result_combos()
        if not combos:
            return
        current = self.sender()
        index = next((offset for offset, combo in enumerate(combos) if combo is current), 0)
        target = combos[(index + delta) % len(combos)]
        target.setFocus(Qt.FocusReason.TabFocusReason)
        for row in range(self.pairings.rowCount()):
            if self.pairings.cellWidget(row, 3) is target:
                self.pairings.selectRow(row)
                break

    def _focus_result_combo(self, index: int = 0) -> None:
        combos = self._result_combos()
        if not combos:
            return
        target = combos[index % len(combos)]
        target.setFocus(Qt.FocusReason.TabFocusReason)
        self.tabs.setCurrentIndex(1)

    def _selected_player_id(self) -> str | None:
        row = self.players_table.currentRow()
        if row < 0:
            return None
        item = self.players_table.item(row, 2)
        if item is None:
            return None
        value = item.data(_USER_ROLE)
        return str(value) if value else None

    def _selected_player(self) -> Player | None:
        player_id = self._selected_player_id()
        if player_id is None:
            return None
        return self._manager.state.player_map().get(player_id)

    def _set_selected_status(self, status: PlayerStatus) -> None:
        player_id = self._selected_player_id()
        if player_id is None:
            self.status.setText("Выберите игрока в списке.")
            return
        try:
            player = self._manager.set_player_status(player_id, status)
            self.status.setText(f"{player.name}: {_STATUS_LABELS.get(status, status.value)}")
            self._refresh()
        except KeyError as exc:
            self.status.setText(str(exc))

    def _schedule_half_bye(self) -> None:
        player_id = self._selected_player_id()
        if player_id is None:
            self.status.setText("Выберите игрока для ½ bye.")
            return
        try:
            player = self._manager.schedule_bye(player_id, RESULT_HPB)
            self.status.setText(f"{player.name}: ½ bye на следующий тур.")
            self._refresh()
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))

    def _add_player_dialog(self) -> None:
        self._begin_player_entry()

    def _on_player_double_clicked(self, row: int, column: int) -> None:
        del column
        self._edit_player_at_row(row)

    def _player_id_at_row(self, row: int) -> str | None:
        item = self.players_table.item(row, 2)
        if item is None or item.data(_DRAFT_ROLE):
            return None
        value = item.data(_USER_ROLE)
        return str(value) if value else None

    def _edit_player_at_row(self, row: int) -> bool:
        player_id = self._player_id_at_row(row)
        if player_id is None:
            return False
        self.players_table.selectRow(row)
        self._edit_player_dialog()
        return True

    def _edit_player_dialog(self) -> None:
        player = self._selected_player()
        if player is None:
            self.status.setText("Выберите игрока в списке.")
            return
        dialog = PlayerDialog(self, player)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            self._manager.update_player(player.player_id, **values)
            self._refresh()
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))

    def _sort_starting_list(self) -> None:
        try:
            self._ensure_seed_manager()
            players = self._manager.sort_starting_list()
            self.status.setText(
                f"Стартовый список: {len(players)} игроков по рейтингу (ст. № 1 — сильнейший)."
            )
            self._refresh()
        except ValueError as exc:
            self.status.setText(str(exc))

    def _ensure_seed_manager(self) -> None:
        if self._manager.players or self.players_edit.toPlainText().strip():
            try:
                self._ensure_manager_from_text()
                return
            except ValueError:
                pass
        self._manager = TournamentManager(new_tournament_state((), self._settings_from_controls()))

    def _sync_players_edit(self) -> None:
        text = "\n".join(
            f"{player.name}|{player.rating}|{player.team or ''}" for player in self._manager.players
        )
        if self.players_edit.toPlainText() != text:
            self.players_edit.setPlainText(text)

    def _on_system_changed(self) -> None:
        system = self.system.currentData()
        self.cycles.setEnabled(
            self._manager.current_round == 0 and system is PairingSystem.ROUND_ROBIN
        )
        no_color = system is PairingSystem.SWISS_NO_COLOR
        self.pairings.setHorizontalHeaderLabels(
            ("Доска", "Игрок 1", "Игрок 2", "Результат", "Примечание")
            if no_color
            else ("Доска", "Белые", "Чёрные", "Результат", "Примечание")
        )
        self.invert_button.setText("Места" if no_color else "Цвета")
        if self._manager.current_round == 0:
            self._apply_header_settings()

    def _on_round_changed(self, value: int) -> None:
        self._view_round = value
        if not self._syncing:
            self._refresh_pairings()

    def _import_csv_dialog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Импорт CSV", "", "CSV (*.csv);;All (*.*)")
        if not path:
            return
        text = Path(path).read_text(encoding="utf-8-sig")
        self.import_csv_text(text)

    def _import_xlsx_dialog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Импорт игроков из Excel",
            "",
            "Excel (*.xlsx *.xls *.xlsm);;Excel 2007+ (*.xlsx);;Excel 97-2003 (*.xls);;All (*.*)",
        )
        if not path:
            return
        try:
            report = import_players_from_excel(path)
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Excel", str(exc))
            self.status.setText(str(exc))
            return
        self._apply_import(report.players, report.errors, report.duplicates)

    def _delete_round_dialog(self) -> None:
        if self._manager.current_round < 1:
            self.status.setText("Нет туров для удаления.")
            return
        target = self._view_round
        last = self._manager.current_round
        if target < 1:
            target = last
        message = (
            f"Удалить тур {target} и все последующие (до {last})?\n"
            "Игроки останутся. После удаления первого тура можно сменить систему жеребьёвки."
            if target < last
            else (
                f"Удалить тур {target}?\n"
                "Игроки останутся. Если это был первый тур, можно сменить систему жеребьёвки."
            )
        )
        answer = QMessageBox.question(self, "Удалить тур", message)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            current = self._manager.delete_rounds_from(target, reason="коррекция тура")
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self._view_round = max(1, current)
        if current == 0:
            self.status.setText("Туры удалены. Игроки на месте — можно сменить систему и сгенерировать заново.")
        else:
            self.status.setText(f"Удалены туры с {target}. Текущий тур: {current}.")
        self._refresh()

    def _import_google_dialog(self) -> None:
        dialog = GoogleSheetDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self.import_google_url(dialog.url())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Google Таблица", str(exc))
            self.status.setText(str(exc))

    def _save_dialog(self) -> None:
        default = self._path or Path("tournament.tournament.json")
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Сохранить турнир",
            str(default),
            "JSON (*.json);;TRF16 для Swiss-Manager (*.trf)",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".trf") or "TRF16" in selected:
                self._ensure_manager_from_text()
                self._apply_header_settings()
                saved = save_trf(self._manager.state, path)
                self.status.setText(
                    f"TRF16: {saved}. В Swiss-Manager: Other → FIDE Data Import. "
                    "Нативный .TUN/.TUNX записать нельзя (закрытый формат с лицензией)."
                )
                return
            self.save_to(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Сохранение", str(exc))

    def _open_dialog(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Открыть турнир",
            "",
            "Турнир (*.json *.trf *.txt *.tunx *.turx *.tun);;"
            "JSON (*.json);;"
            "TRF16 (*.trf *.txt);;"
            "Swiss-Manager (*.tunx *.turx *.tun);;"
            "Все (*.*)",
        )
        if not path:
            return
        try:
            self.load_from(path)
        except (ValueError, OSError, KeyError) as exc:
            QMessageBox.warning(self, "Открытие", str(exc))

    def _export_dialog(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Экспорт Excel", "tournament.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        try:
            exported = self.export_xlsx_to(path)
            self.status.setText(f"Excel: {exported}")
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(exported.resolve())))
            if not opened:
                self.status.setText(f"Excel сохранён: {exported} (не удалось открыть автоматически)")
        except (ValueError, OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "Excel", str(exc))

    def _export_trf_dialog(self) -> None:
        try:
            self._ensure_manager_from_text()
        except ValueError as exc:
            QMessageBox.warning(self, "TRF", str(exc))
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Экспорт TRF", "tournament.trf", "TRF (*.trf);;Text (*.txt)")
        if not path:
            return
        Path(path).write_bytes(self._manager.trf_text().encode("utf-8-sig"))
        self.status.setText(
            f"TRF16: {path}. В Swiss-Manager откройте через FIDE Data Import. "
            "Файл .TUN/.TUNX записать нельзя."
        )

    def _properties_dialog(self) -> None:
        dialog = TournamentPropertiesDialog(self._manager.state.settings, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.name_edit.setText(values["name"])
        settings = self._settings_from_controls()
        settings = TournamentSettings(
            name=values["name"],
            system=settings.system,
            declared_rounds=settings.declared_rounds,
            rr_cycles=settings.rr_cycles,
            seed=settings.seed,
            list_closed=settings.list_closed,
            site=values["site"],
            arbiter=values["arbiter"],
            time_control=values["time_control"],
            initial_color=settings.initial_color,
            pairing_engine=settings.pairing_engine,
        )
        self._manager.update_settings(settings)
        self.status.setText(f"Свойства: {settings.name}")

    def _edit_pairs_dialog(self) -> None:
        current = self._manager.round_pairings(self._view_round)
        if not current:
            self.status.setText("Сначала сгенерируйте тур.")
            return
        dialog = PairingEditDialog(self._manager.players, current, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        if not dialog.reason():
            QMessageBox.warning(self, "Пары", "Укажите причину изменения пар.")
            return
        try:
            warnings = self._manager.replace_round_pairings(
                self._view_round, dialog.pairings(self._view_round), reason=dialog.reason()
            )
            text = "Пары изменены."
            if warnings:
                text += " " + "; ".join(warnings)
            self.status.setText(text)
            self._refresh()
        except ValueError as exc:
            self.status.setText(str(exc))

    def _invert_selected(self) -> None:
        row = self.pairings.currentRow()
        if row < 0:
            no_color = self.system.currentData() is PairingSystem.SWISS_NO_COLOR
            self.status.setText(
                "Выберите доску, чтобы поменять местами."
                if no_color
                else "Выберите доску, чтобы поменять цвета."
            )
            return
        item = self.pairings.item(row, 0)
        if item is None:
            return
        try:
            reason = (
                "коррекция мест"
                if self.system.currentData() is PairingSystem.SWISS_NO_COLOR
                else "коррекция цвета"
            )
            self._manager.invert_colors(
                self._view_round, int(item.text()), reason=reason
            )
            self.status.setText(f"Места доски {item.text()} изменены.")
            self._refresh()
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))

    def _copy_pairings(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._manager.pairings_text(self._view_round))
        self.status.setText("Пары скопированы в буфер обмена.")

    def _sync_controls_from_state(self) -> None:
        settings = self._manager.state.settings
        self._syncing = True
        try:
            index = self.system.findData(settings.system)
            if index >= 0:
                self.system.setCurrentIndex(index)
            self.rounds.setValue(settings.declared_rounds)
            self.cycles.setValue(settings.rr_cycles)
            self.seed.setValue(settings.seed)
            self.name_edit.setText(settings.name)
            self.close_list.setChecked(settings.list_closed)
            self._sync_players_edit()
        finally:
            self._syncing = False


def _board_name(player: Player | None) -> str:
    if player is None:
        return "BYE"
    title = f"{player.title} " if player.title else ""
    rating = f" ({player.rating})" if player.rating else ""
    return f"{player.start_number}. {title}{player.name}{rating}".strip()


def _open_status(path: Path, name: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tunx", ".turx", ".tun"}:
        return (
            f"Открыто {name} из Swiss-Manager ({path.name}). "
            "Сохраните JSON для работы здесь или TRF16, чтобы вернуть турнир в Swiss-Manager. "
            "Запись .TUN/.TUNX не поддерживается."
        )
    if suffix in {".trf", ".txt"}:
        return f"Открыто {name} из TRF16 ({path.name})."
    return f"Открыто: {path}"
