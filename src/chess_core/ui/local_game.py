"""Thin PyQt adapter for a local game service."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.clock import GameClockService
from chess_core.app.engine import BestMove, EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.app.engine_play import requires_blocker, resolve_engine_turn
from chess_core.app.game import GameStatus, LocalGameService, material_winner
from chess_core.app.pgn_database import PgnDatabaseService
from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, PassAction, PlaceBlockerAction, Turn
from chess_core.core.notation import normalize_engine_token, parse_square, parse_uci
from chess_core.core.piece import PieceSide
from chess_core.core.rules import VictoryKind
from chess_core.core.state import GameState
from chess_core.core.time_control import TimeControlConfig
from chess_core.infra.engines.discovery import EngineDescriptor
from chess_core.infra.storage.pgn_files import (
    default_games_dir,
    read_pgn_text,
    write_chessbase_pgn,
)
from chess_core.ui.engine_bridge import EngineBridge
from chess_core.ui.piece_keys import drop_flip_map, droppable_type_names, piece_asset_key
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketWidget
from chess_core.ui.widgets.promotion_menu import choose_promotion_move
from chess_core.ui.widgets.time_control_dialog import TimeControlDialog
from chess_core.ui.theme import tighten_wrapping_label

_TERMINAL_STATUSES = frozenset(
    (
        GameStatus.CHECKMATE,
        GameStatus.STALEMATE,
        GameStatus.REPETITION_DRAW,
        GameStatus.MATERIAL_WIN,
        GameStatus.TRY_WIN,
        GameStatus.KING_CAPTURE_WIN,
    )
)


class _MonoClock:
    def now_ms(self) -> int:
        return int(time.monotonic() * 1000)


class LocalGameWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
        discovered: list[EngineDescriptor] | None = None,
        *,
        allow_temporary_variations: bool = False,
        analysis_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._discovered = discovered
        self._allow_temporary_variations = allow_temporary_variations
        self._analysis_mode = analysis_mode
        self._service: LocalGameService | None = None
        self._selected: int | None = None
        self._time_control = TimeControlConfig.blitz()
        self._clock_service: GameClockService | None = None
        self._clock_settings_open = False
        self.board = BoardWidget()
        self.board.set_piece_drag_enabled(True)
        self.status = QLabel()
        self.status.setObjectName("gameStatus")
        tighten_wrapping_label(self.status)
        self.move_list = MoveListWidget()
        self.clock_widget = GameClockWidget()
        self.clock_off_button = QPushButton("Без времени")
        self.clock_off_button.setToolTip("Нажмите, чтобы включить контроль времени")
        self.clock_off_button.hide()
        self.evaluation_bar = EvaluationBarWidget()
        self.instructions = QLabel(
            "Ход: щёлкните фигуру и клетку или перетащите фигуру зажатой ЛКМ; "
            "пустая клетка — сброс диска. "
            "Щёлкните часы в любой момент, чтобы сменить контроль или отключить его. "
            "F — перевернуть доску; F11 — полный экран; "
            "H — подсветка хода движка; G — оценка; "
            "ПКМ на комодае — перевернуть фигуру при сбросе; "
            "Ctrl+Z — отмена хода; R — новая игра после окончания. "
            "После партии запись можно скопировать или сохранить в файл."
        )
        self.instructions.setObjectName("gameHint")
        tighten_wrapping_label(self.instructions)
        self.vs_computer = QCheckBox("Одиночная игра")
        self.vs_computer.setToolTip(
            "Играть против движка этого режима. "
            "Перед включением переверните доску (F), чтобы сесть за чёрных."
        )
        self.show_eval = QCheckBox("Оценка (G)")
        self.show_eval.setToolTip("Показать столбик оценки позиции. Клавиша G.")
        self.show_eval.setChecked(False)
        self.black_pocket = PocketWidget(PieceSide.BLACK)
        self.white_pocket = PocketWidget(PieceSide.WHITE)
        self._hand_rail = QWidget()
        self._hand_rail_layout = QVBoxLayout(self._hand_rail)
        self._hand_rail_layout.setContentsMargins(0, 0, 0, 0)
        self._hand_rail.hide()
        self.new_game_button = QPushButton("Новая игра / Сброс")
        self.live_button = QPushButton("К текущей позиции")
        self.mainline_button = QPushButton("Вернуться к основной линии")
        self.mainline_button.setToolTip("Удалить временную ветку и вернуться к загруженной записи")
        self.mainline_button.hide()
        self.quit_button = QPushButton("Выйти")

        main_split = QSplitter()
        board_panel = QWidget()
        board_layout = QVBoxLayout(board_panel)
        board_row = QWidget()
        board_row_layout = QHBoxLayout(board_row)
        board_row_layout.setContentsMargins(0, 0, 0, 0)
        board_row_layout.addWidget(self.board, 1)
        board_row_layout.addWidget(self._hand_rail, 0, Qt.AlignmentFlag.AlignVCenter)
        board_layout.addWidget(self.status)
        board_layout.addWidget(board_row, 1)
        board_layout.addWidget(self.instructions)
        controls = QHBoxLayout()
        controls.addWidget(self.new_game_button)
        controls.addWidget(self.live_button)
        controls.addWidget(self.mainline_button)
        controls.addStretch()
        controls.addWidget(self.quit_button)
        board_layout.addLayout(controls)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.addWidget(self.clock_widget)
        sidebar_layout.addWidget(self.clock_off_button)
        sidebar_layout.addWidget(self.evaluation_bar)
        sidebar_layout.addWidget(self.vs_computer)
        sidebar_layout.addWidget(self.show_eval)
        log_title = QLabel("Запись партии")
        log_title.setObjectName("panelTitle")
        sidebar_layout.addWidget(log_title)
        sidebar_layout.addWidget(self.move_list)
        export_row = QHBoxLayout()
        self.copy_record_button = QPushButton("Копировать")
        self.copy_record_button.setToolTip("Скопировать запись партии в буфер обмена")
        self.save_record_button = QPushButton("Сохранить…")
        self.save_record_button.setToolTip("Сохранить партию как PGN (ChessBase 16)")
        self.add_to_database_button = QPushButton("В базу…")
        self.add_to_database_button.setToolTip("Добавить партию в существующую или новую PGN-базу")
        export_row.addWidget(self.copy_record_button)
        export_row.addWidget(self.save_record_button)
        export_row.addWidget(self.add_to_database_button)
        sidebar_layout.addLayout(export_row)
        self.export_hint = QLabel("После партии скопируйте или сохраните запись.")
        self.export_hint.setObjectName("gameHint")
        tighten_wrapping_label(self.export_hint)
        sidebar_layout.addWidget(self.export_hint)
        if self._analysis_mode:
            self.clock_widget.hide()
            self.clock_off_button.hide()
            self.vs_computer.hide()
            self.export_hint.setText("Запись можно скопировать, сохранить в файл или добавить в базу.")

        main_split.addWidget(board_panel)
        main_split.addWidget(sidebar)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes((720, 240))
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.addWidget(main_split)

        self.board.square_clicked.connect(self._on_square)
        self.white_pocket.piece_chosen.connect(self._on_pocket)
        self.black_pocket.piece_chosen.connect(self._on_pocket)
        self.clock_widget.clicked.connect(self._open_clock_settings)
        self.clock_off_button.clicked.connect(self._open_clock_settings)
        self.new_game_button.clicked.connect(self.reset_game)
        self.live_button.clicked.connect(self._go_live)
        self.mainline_button.clicked.connect(self._return_to_mainline)
        self.quit_button.clicked.connect(self._quit)
        self.move_list.revision_selected.connect(self._on_revision_selected)
        self.copy_record_button.clicked.connect(self.copy_transcript)
        self.save_record_button.clicked.connect(self.save_transcript)
        self.add_to_database_button.clicked.connect(self.add_transcript_to_database)
        self._copy_record_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        self._copy_record_shortcut.activated.connect(self.copy_transcript)
        self._save_record_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_record_shortcut.activated.connect(self.save_transcript)
        self._flip_shortcut = QShortcut(QKeySequence("F"), self)
        self._flip_shortcut.activated.connect(self.flip_board)
        self._shift_flip_shortcut = QShortcut(QKeySequence("Shift+F"), self)
        self._shift_flip_shortcut.activated.connect(self.flip_board)
        self._reset_shortcut = QShortcut(QKeySequence("R"), self)
        self._reset_shortcut.activated.connect(self.reset_finished_game)
        self._undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self.undo_move)
        self._hints_shortcut = QShortcut(QKeySequence("H"), self)
        self._hints_shortcut.activated.connect(self._toggle_hints)
        self._eval_shortcut = QShortcut(QKeySequence("G"), self)
        self._eval_shortcut.activated.connect(self._toggle_eval)
        self.vs_computer.toggled.connect(self._on_vs_computer)
        self.show_eval.toggled.connect(self._on_show_eval)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._tick_clock_display)
        if not self._analysis_mode:
            self._ui_timer.start()

        self._hints_enabled = False
        self._eval_visible = False
        self._engine_bridge: EngineBridge | None = None
        self._engine_squares: set[int] = set()
        self._last_move_squares: set[int] = set()
        self._vs_computer = False
        self._mode_id = mode_id
        self._human_side = PieceSide.WHITE
        self._pending_move: MoveAction | None = None
        self._pending_engine_turn: Turn | None = None
        self._engine_preview: tuple[int | None, int | None] | None = None
        self._play_revision = -1
        self._play_limit = SearchLimit(movetime_ms=400)
        self._engine_move_delay_ms = 380
        self._engine_play_timer = QTimer(self)
        self._engine_play_timer.setSingleShot(True)
        self._engine_play_timer.timeout.connect(self._commit_pending_engine_turn)
        self.evaluation_bar.hide()

        self.set_mode(mode_id)

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        mode = self._resolve(mode_id)
        if str(mode.initial_extras.get("match_kind", "single")) in {"bughouse", "hand_and_brain"}:
            self._service = LocalGameService(mode)
            self._clock_service = GameClockService(self._time_control, _MonoClock())
            self._selected = None
            self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
            if str(mode.initial_extras.get("match_kind")) == "bughouse":
                self.status.setText(
                    "Bughouse играется во вкладке «Сеть»: один клиент может сесть "
                    "сразу за две доски (например A·белые и B·чёрные). "
                    "Свободные места хост заполняет Fairy-Stockfish — одним процессом "
                    "или двумя, по галочке."
                )
            else:
                self.status.setText(
                    "Этот режим рассчитан на 4 клиента в сети. Откройте раздел «Сетевая игра»."
                )
            self.board.set_position({})
            self.board.clear_highlights()
            self._cancel_pending_engine_turn()
            self._last_move_squares = set()
            self._hide_hands()
            self.clock_widget.setVisible(False)
            self.clock_off_button.setVisible(False)
            self.evaluation_bar.set_evaluation(None)
            self.evaluation_bar.hide()
            self.vs_computer.setEnabled(False)
            self.show_eval.setEnabled(False)
            self.copy_record_button.setEnabled(False)
            self.save_record_button.setEnabled(False)
            self._shutdown_engine()
            return
        self._service = LocalGameService(
            mode,
            allow_temporary_variations=self._allow_temporary_variations,
        )
        self._clock_service = GameClockService(self._time_control, _MonoClock())
        self._play_limit = (
            SearchLimit(movetime_ms=10_000) if mode_id == "gobblet" else SearchLimit(movetime_ms=400)
        )
        self._selected = None
        self._pending_move = None
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
        self.clock_widget.setVisible(not self._analysis_mode and self._time_control.is_timed)
        self.clock_off_button.setVisible(not self._analysis_mode and not self._time_control.is_timed)
        self.vs_computer.setEnabled(not self._analysis_mode)
        self.show_eval.setEnabled(True)
        self.evaluation_bar.setVisible(self._eval_visible)
        self._update_mode_hint(mode)
        self._bind_engine(restart=True)
        self._refresh()

    def _update_mode_hint(self, mode: GameMode) -> None:
        from chess_core.core.turn import StepKind

        base = (
            "Ход: щёлкните фигуру и клетку, либо пустую клетку для сброса диска. "
            "Щёлкните часы в любой момент, чтобы сменить контроль или отключить его. "
            "F — перевернуть доску; F11 — полный экран; "
            "H — подсветка хода движка; G — оценка; "
            "ПКМ на комодае — перевернуть фигуру при сбросе; "
            "Ctrl+Z — отмена хода; R — новая игра после окончания. "
            "После партии запись можно скопировать или сохранить в файл."
        )
        has_duck = any(
            step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps
        )
        if not has_duck:
            self.instructions.setText(base)
            return
        if mode.initial_extras.get("fairy_duck_rules"):
            self.instructions.setText(
                "Duck (Fairy): шахов нет, короля можно оставить под боем, "
                "партия кончается его взятием. После хода фигурой кликните клетку для утки. "
                "Одиночная игра идёт против Fairy-Stockfish ALLVARS, если бинарник найден, "
                "иначе против встроенного поиска. " + base
            )
            return
        self.instructions.setText(
            "Duck (ядро проекта): обычные шахи и мат. Ходы, после которых король "
            "остаётся под боем, запрещены, даже если утка могла бы закрыть линию. "
            "Галочка «Fairytale» в списке режимов с Duck включает королевское взятие "
            "и Fairy-движок. Без Duck та же галочка — ходы ладьи/слона/коня по файлу. "
            "После хода фигурой кликните клетку для утки. " + base
        )

    def enable_engine_analysis(self, enabled: bool = True) -> None:
        self._hints_enabled = enabled
        self._eval_visible = enabled
        self.evaluation_bar.setVisible(enabled)
        self.show_eval.blockSignals(True)
        self.show_eval.setChecked(enabled)
        self.show_eval.blockSignals(False)
        self._sync_analysis()

    def _wants_analysis(self) -> bool:
        return self._hints_enabled or self._eval_visible

    def _sync_analysis(self) -> None:
        self._bind_engine()
        if self._wants_analysis() or self._vs_computer:
            self._request_engine()
            return
        self._engine_squares = set()
        self.evaluation_bar.set_evaluation(None)
        if self._service is not None:
            self._apply_highlights(self._service.status())

    def _toggle_hints(self) -> None:
        if self._network_only():
            return
        self._hints_enabled = not self._hints_enabled
        if not self._hints_enabled:
            self._engine_squares = set()
            if self._service is not None:
                self._apply_highlights(self._service.status())
        self._sync_analysis()

    def _toggle_eval(self) -> None:
        if not self.show_eval.isEnabled():
            return
        self.show_eval.toggle()

    def _on_show_eval(self, checked: bool) -> None:
        self._eval_visible = checked
        self.evaluation_bar.setVisible(checked)
        if not checked:
            self.evaluation_bar.set_evaluation(None)
        self._sync_analysis()

    def _on_vs_computer(self, checked: bool) -> None:
        self._vs_computer = checked
        if checked:
            self._human_side = (
                PieceSide.WHITE
                if self.board.orientation is BoardOrientation.WHITE
                else PieceSide.BLACK
            )
            self._engine_squares = set()
            self._cancel_pending_engine_turn()
        self._pending_move = None
        self._bind_engine()
        self._refresh()

    def _network_only(self) -> bool:
        if self._service is None:
            return False
        return str(self._service.mode.initial_extras.get("match_kind", "single")) in {
            "bughouse",
            "hand_and_brain",
        }

    def _human_may_move(self) -> bool:
        if not self._vs_computer or self._service is None:
            return True
        return self._service.state.side_to_move is self._human_side

    def _bind_engine(self, *, restart: bool = False) -> None:
        if self._service is None or self._network_only():
            self._shutdown_engine()
            return
        if not self._wants_analysis() and not self._vs_computer:
            self._shutdown_engine()
            return
        if self._engine_bridge is not None and not restart:
            return
        service = EngineAnalysisService.for_mode(self._service.mode, self._discovered)
        self._shutdown_engine()
        self._engine_bridge = EngineBridge(service, self)
        self._engine_bridge.analysis_ready.connect(self._on_analysis)

    def _shutdown_engine(self) -> None:
        if self._engine_bridge is None:
            return
        self._engine_bridge.analysis_ready.disconnect(self._on_analysis)
        self._engine_bridge.shutdown()
        self._engine_bridge.deleteLater()
        self._engine_bridge = None

    def closeEvent(self, event) -> None:  # noqa: ANN001 - Qt override
        self._cancel_pending_engine_turn()
        self._shutdown_engine()
        super().closeEvent(event)

    def _request_engine(self) -> None:
        if self._engine_bridge is None or self._service is None:
            return
        if not self.service.is_live or self.service.status() in _TERMINAL_STATUSES:
            self._engine_squares = set()
            return
        if self._vs_computer and self._human_may_move():
            return
        play = self._vs_computer and not self._human_may_move()
        if not play and not self._wants_analysis():
            return
        if play:
            self._engine_squares = set()
        purpose = "play" if play else "analyze"
        self._play_revision = self.service.record.live_revision if play else -1
        limit = self._play_limit if play else SearchLimit(movetime_ms=250)
        self._engine_bridge.request_analysis(
            EngineRequest(self.service.state, limit, purpose=purpose, revision=self._play_revision)
        )

    def _on_analysis(self, result: BestMove) -> None:
        if self._service is None:
            return
        if self._vs_computer and result.purpose != "play":
            return
        if self._eval_visible:
            self.evaluation_bar.set_evaluation(result.evaluation, error=result.error)
        shape = self._service.mode.board.shape
        if self._hints_enabled:
            self._engine_squares = _engine_squares(result.move_uci, shape.files, shape.ranks)
        else:
            self._engine_squares = set()
        self._apply_highlights(self._service.status())
        if result.purpose != "play" or not self._vs_computer:
            return
        if result.revision != self.service.record.live_revision:
            return
        if not self.service.is_live or self._human_may_move():
            return
        if self.service.status() in _TERMINAL_STATUSES:
            return
        turn = result.turn if isinstance(result.turn, Turn) else resolve_engine_turn(self.service.state, result)
        if turn is None:
            if self._eval_visible:
                self.evaluation_bar.set_evaluation(result.evaluation, error="движок не смог выбрать ход")
            else:
                self.status.setText("Движок не смог выбрать ход.")
            return
        self._queue_engine_turn(turn)

    def _queue_engine_turn(self, turn: Turn) -> None:
        assert self._service is not None
        self._pending_engine_turn = turn
        shape = self._service.mode.board.shape
        self._engine_preview = _preview_squares(turn, shape.files)
        self._apply_highlights(self._service.status())
        if self._engine_move_delay_ms <= 0:
            self._commit_pending_engine_turn()
            return
        self._engine_play_timer.start(self._engine_move_delay_ms)

    def _commit_pending_engine_turn(self) -> None:
        turn = self._pending_engine_turn
        self._pending_engine_turn = None
        self._engine_preview = None
        if turn is None or self._service is None:
            return
        if not self._vs_computer or not self.service.is_live or self._human_may_move():
            return
        if self.service.status() in _TERMINAL_STATUSES:
            return
        self._last_move_squares = _action_squares(turn.actions, self._service.mode.board.shape.files)
        self._commit_side(lambda: self.service.play_turn(turn))
        self._selected = None
        self._pending_move = None
        self._refresh()

    def _cancel_pending_engine_turn(self) -> None:
        self._engine_play_timer.stop()
        self._pending_engine_turn = None
        self._engine_preview = None

    def _apply_highlights(self, game_status: GameStatus) -> None:
        assert self._service is not None
        legal_destinations: set[int] = set()
        shape = self._service.mode.board.shape
        if self._engine_preview is not None:
            origin, dest = self._engine_preview
            selected = origin
            legal_destinations = {dest} if dest is not None else set()
        elif self._pending_move is not None and self.service.can_play:
            legal_destinations = _duck_targets(self._service.state, self._pending_move)
            selected = self._pending_move.from_square.index(shape.files)
        elif self._selected is not None and self.service.can_play:
            legal_destinations = {
                move.to_square.index(shape.files)
                for move in self._service.selected_moves
            }
            selected = self._selected
        elif self.pocket.selected_type() is not None and self.service.can_play:
            name = self.pocket.selected_type()
            legal_destinations = {
                action.to_square.index(shape.files)
                for action in self._service.legal_drops()
                if action.piece_type.name == name
            }
            selected = self._selected if self.service.can_play else None
        elif self._service.mode.initial_extras.get("click_drops") and self.service.can_play:
            legal_destinations = {
                action.to_square.index(shape.files)
                for action in self._service.legal_drops()
            }
            selected = None
        else:
            selected = self._selected if self.service.can_play else None
        check_squares: set[int] = set()
        if game_status in (GameStatus.CHECK, GameStatus.CHECKMATE):
            royal = self._service.mode.royal_type
            for index, piece in self._service.state.board_state.cells.items():
                if (
                    piece is not None
                    and piece.side is self._service.state.side_to_move
                    and piece.piece_type.name == royal
                ):
                    check_squares.add(index)
        if not self.service.can_play and self._engine_preview is None:
            selected = None
        self.board.set_highlights(
            selected=selected,
            legal_destinations=legal_destinations,
            check_squares=check_squares,
            last_move_squares=self._last_move_squares,
            engine_squares=self._engine_squares if self._hints_enabled else set(),
        )

    def load_position(self, state: GameState) -> None:
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self.service.load_position(state)
        if self._clock_service is not None:
            self._clock_service = GameClockService(
                self._time_control,
                _MonoClock(),
                starting_side=self.service.state.side_to_move,
            )
        self._selected = None
        self._refresh()

    def load_pgn(self, text: str, *, game_index: int = 0) -> None:
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self.service.import_pgn(text, game_index=game_index)
        self._selected = None
        self._refresh()

    def load_pgn_game(self, game) -> None:
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self.service.import_pgn_game(game)
        self._selected = None
        self._refresh()

    def _return_to_mainline(self) -> None:
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self.service.return_to_mainline()
        self._selected = None
        self._refresh()

    @property
    def service(self) -> LocalGameService:
        if self._service is None:
            raise RuntimeError("No game mode is loaded")
        return self._service

    def apply_time_control(self, config: TimeControlConfig) -> bool:
        if self._analysis_mode or self._network_only():
            return False
        if self._service is not None and not self.service.is_live:
            return False
        self._time_control = config
        side = self.service.state.side_to_move if self._service is not None else PieceSide.WHITE
        start_now = bool(
            config.is_timed
            and self._service is not None
            and self.service.record.live_revision > 0
        )
        if self._clock_service is None:
            self._clock_service = GameClockService(config, _MonoClock(), starting_side=side)
        self._clock_service.reconfigure(config, start_now=start_now, running_side=side)
        self._sync_clock_with_game()
        return True

    def reset_game(self) -> None:
        self.service.reset()
        if self._clock_service is not None:
            self._clock_service = GameClockService(self._time_control, _MonoClock())
        self._selected = None
        self._pending_move = None
        self._cancel_pending_engine_turn()
        self._last_move_squares = set()
        self._refresh()

    def undo_move(self) -> None:
        if not self.service.can_undo():
            return
        self._cancel_pending_engine_turn()
        if self._vs_computer:
            self.service.undo()
            if self.service.can_undo() and not self._human_may_move():
                self.service.undo()
        else:
            self.service.undo()
        self._selected = None
        self._pending_move = None
        self._last_move_squares = set()
        self._refresh()

    def reset_finished_game(self) -> bool:
        if self.service.status() not in _TERMINAL_STATUSES:
            self.status.setText("Игра ещё продолжается — клавиша R не сбрасывает позицию.")
            return False
        self.reset_game()
        return True

    def flip_board(self) -> None:
        self.board.flip_orientation()
        self._layout_hands()
        self._refresh()

    def show_revision(self, revision: int) -> None:
        """Show one ply of the loaded game. ``0`` is the start position."""
        if self._service is None:
            return
        live = self.service.record.live_revision
        if not 0 <= revision <= live:
            return
        self._cancel_pending_engine_turn()
        self.service.go_to_revision(revision)
        self._selected = None
        self._refresh()

    def _go_live(self) -> None:
        self.service.go_live()
        self._refresh()

    def _on_revision_selected(self, revision: int) -> None:
        self._cancel_pending_engine_turn()
        self.service.go_to_revision(revision)
        self._selected = None
        self._refresh()

    def copy_transcript(self) -> str | None:
        if self._service is None or self.service.record.live_revision == 0:
            return None
        text = self.service.export_transcript()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.export_hint.setText("Запись скопирована в буфер обмена.")
        return text

    def save_transcript(self, path: Path | None = None) -> bool:
        if self._service is None or self.service.record.live_revision == 0:
            return False
        text = self.service.export_transcript()
        if path is None:
            suggested = self.service.transcript_filename()
            chosen, _filter = QFileDialog.getSaveFileName(
                self,
                "Сохранить партию как PGN",
                suggested,
                "PGN ChessBase (*.pgn);;Текстовая запись (*.txt);;Все файлы (*.*)",
            )
            if not chosen:
                return False
            path = Path(chosen)
        try:
            if path.suffix.lower() == ".pgn":
                write_chessbase_pgn(path, text)
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось сохранить запись", str(exc))
            return False
        self.export_hint.setText(f"Запись сохранена: {path.name}")
        return True

    def add_transcript_to_database(self, path: Path | None = None) -> bool:
        if self._service is None or self.service.record.live_revision == 0:
            return False
        text = self.service.export_transcript()
        if path is None:
            dialog = QFileDialog(self, "Добавить партию в PGN-базу")
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dialog.setNameFilter("База ChessBase / PGN (*.pgn);;Все файлы (*.*)")
            dialog.setDefaultSuffix("pgn")
            dialog.setDirectory(str(default_games_dir()))
            dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, True)
            if not dialog.exec():
                return False
            selected = dialog.selectedFiles()
            if not selected:
                return False
            path = Path(selected[0])
        if path.suffix.lower() != ".pgn":
            path = path.with_suffix(".pgn")
        service = PgnDatabaseService()
        extra = tuple(item.game for item in service.parse_text(text, source=path.name))
        try:
            existing = read_pgn_text(path) if path.is_file() else ""
            merged = service.append_to_database(existing, extra)
            write_chessbase_pgn(path, merged)
        except OSError as exc:
            QMessageBox.warning(self, "Не удалось обновить базу", str(exc))
            return False
        added = service.added_count(existing, merged)
        if added == 0:
            self.export_hint.setText(f"Эта партия уже есть в {path.name}.")
        else:
            self.export_hint.setText(f"Партия добавлена в базу {path.name}.")
        return True

    def _sync_export_controls(self, game_status: GameStatus) -> None:
        has_moves = self._service is not None and self.service.record.live_revision > 0
        self.copy_record_button.setEnabled(has_moves)
        self.save_record_button.setEnabled(has_moves)
        self.add_to_database_button.setEnabled(has_moves)
        if game_status in _TERMINAL_STATUSES:
            self.export_hint.setText("Партия окончена — скопируйте или сохраните запись.")
        elif has_moves:
            self.export_hint.setText("Запись можно скопировать или сохранить в любой момент.")
        else:
            self.export_hint.setText("После партии скопируйте или сохраните запись.")

    def _quit(self) -> None:
        window = self.window()
        if window is not self:
            window.close()
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @property
    def pocket(self) -> PocketWidget:
        if self._service is not None and self._service.state.side_to_move is PieceSide.BLACK:
            return self.black_pocket
        return self.white_pocket

    def _on_pocket(self, piece_type: str) -> None:
        if self._service is None or not self.service.can_play:
            return
        if not self._human_may_move():
            self.pocket.clear_selection()
            return
        sender = self.sender()
        if isinstance(sender, PocketWidget) and sender.side is not self.service.state.side_to_move:
            sender.clear_selection()
            return
        other = self.black_pocket if self.pocket is self.white_pocket else self.white_pocket
        other.clear_selection()
        self._selected = None
        self._service.clear_selection()
        self._refresh()

    def _on_square(self, index: int) -> None:
        if self._service is None or not self.service.can_play:
            return
        if self._service.status() in _TERMINAL_STATUSES:
            return
        if not self._human_may_move():
            return
        if self._pending_move is not None:
            self._finish_duck(index)
            return
        if self.pocket.selected_type() is not None:
            self._try_drop(index)
            return
        shape = self._service.mode.board.shape
        piece = self._service.state.board_state.piece_at(index)
        if (
            self._selected is None
            and piece is None
            and self._service.mode.initial_extras.get("click_drops")
        ):
            self._try_drop(index)
            return
        if self._selected is None:
            if piece is not None and piece.side is self._service.state.side_to_move:
                self._selected = index
                self._service.legal_moves_for_square(index)
                self._refresh()
            return
        if piece is not None and piece.side is self._service.state.side_to_move:
            if self._selected is not None:
                source = Square.from_index(self._selected, shape.files, shape.ranks)
                target = Square.from_index(index, shape.files, shape.ranks)
                candidates = [
                    candidate
                    for candidate in self._service.selected_moves
                    if candidate.from_square == source and candidate.to_square == target
                ]
                if candidates and self._play_from_candidates(candidates, shape):
                    return
            self._selected = index
            self._service.legal_moves_for_square(index)
            self._refresh()
            return
        source = Square.from_index(self._selected, shape.files, shape.ranks)
        target = Square.from_index(index, shape.files, shape.ranks)
        candidates = [
            candidate
            for candidate in self._service.selected_moves
            if candidate.from_square == source and candidate.to_square == target
        ]
        if not self._play_from_candidates(candidates, shape):
            self._service.clear_selection()
            self._selected = None
            self._refresh()

    def _play_from_candidates(self, candidates: list[MoveAction], shape) -> bool:
        if not candidates or self._service is None:
            return False
        move = self._choose_promotion(candidates)
        if move is None:
            return True
        if requires_blocker(self._service.state):
            self._pending_move = move
            self._selected = None
            self._service.clear_selection()
            self._refresh()
            return True
        self._last_move_squares = _action_squares((move,), shape.files)
        self._commit_side(lambda: self._service.play_selected(move))
        self._selected = None
        self._refresh()
        return True

    def _choose_promotion(self, candidates: list[MoveAction]) -> MoveAction | None:
        assert self._service is not None
        piece = (
            self._service.state.board_state.piece_at(self._selected)
            if self._selected is not None
            else None
        )
        return choose_promotion_move(
            candidates,
            parent=self,
            side=self._service.state.side_to_move,
            asset_family=self._service.mode.asset_family,
            unpromoted_type=None if piece is None else piece.piece_type.name,
        )

    def _finish_duck(self, index: int) -> None:
        assert self._service is not None and self._pending_move is not None
        if index not in _duck_targets(self._service.state, self._pending_move):
            piece = self._service.state.board_state.piece_at(index)
            if piece is not None and piece.side is self._service.state.side_to_move:
                self._pending_move = None
                self._selected = index
                self._service.legal_moves_for_square(index)
                self._refresh()
                return
            self._pending_move = None
            self._refresh()
            return
        shape = self._service.mode.board.shape
        duck = PlaceBlockerAction(Square.from_index(index, shape.files, shape.ranks))
        turn = Turn(self._service.state.side_to_move, [self._pending_move, duck])
        self._last_move_squares = _action_squares(turn.actions, shape.files)
        self._pending_move = None
        self._commit_side(lambda: self._service.play_turn(turn))
        self._selected = None
        self._refresh()

    def _try_drop(self, index: int) -> None:
        if self._service is None:
            return
        shape = self._service.mode.board.shape
        target = Square.from_index(index, shape.files, shape.ranks)
        name = self.pocket.selected_type()
        face = self.pocket.selected_face()
        drops = [
            action
            for action in self._service.legal_drops()
            if action.to_square == target
        ]
        if name is not None:
            drops = [
                action
                for action in drops
                if action.piece_type.name == name
                and (action.face == face or (action.face is None and face in {None, name}))
            ]
        drop = drops[0] if len(drops) == 1 else None
        if drop is not None:
            self._last_move_squares = _action_squares((drop,), shape.files)
            self._commit_side(lambda: self._service.play_action(drop))
        self.pocket.clear_selection()
        self._selected = None
        self._refresh()

    def _commit_side(self, play) -> None:
        assert self._service is not None
        side = self._service.state.side_to_move
        play()
        if self._clock_service is not None and self._time_control.is_timed:
            self._clock_service.on_move_committed(side, 0)

    def _tick_clock_display(self) -> None:
        if self._clock_service is None:
            return
        if self._time_control.is_timed:
            self.clock_widget.set_snapshot(
                self._clock_service.snapshot(),
                client_mono_ms=_MonoClock().now_ms(),
            )
        self.clock_widget.set_settings_enabled(self._clock_settings_allowed())

    def _clock_settings_allowed(self) -> bool:
        if self._service is None:
            return False
        if self._analysis_mode or self._network_only():
            return False
        return self.service.is_live

    def _open_clock_settings(self) -> None:
        if self._clock_settings_open or not self._clock_settings_allowed():
            return
        self._clock_settings_open = True
        # Defer so a double-click is not processed inside mousePressEvent.
        QTimer.singleShot(0, self._run_clock_settings_dialog)

    def _run_clock_settings_dialog(self) -> None:
        try:
            if not self._clock_settings_allowed():
                return
            dialog = TimeControlDialog(self._time_control, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.apply_time_control(dialog.config())
        finally:
            self._clock_settings_open = False

    def _sync_clock_with_game(self) -> None:
        if self._analysis_mode:
            self.clock_widget.setVisible(False)
            self.clock_off_button.setVisible(False)
            return
        if self._network_only():
            self.clock_widget.setVisible(False)
            self.clock_off_button.setVisible(False)
            return
        viewing_archive = self._service is not None and not self.service.is_live
        terminal = self._service is not None and self.service.status() in _TERMINAL_STATUSES
        timed = self._time_control.is_timed
        if self._clock_service is not None:
            if not timed or terminal or viewing_archive:
                if not self._clock_service.is_paused:
                    self._clock_service.pause()
            elif self._clock_service.is_paused:
                self._clock_service.resume()
        self.clock_widget.setVisible(timed and not viewing_archive)
        self.clock_off_button.setVisible(not timed and not viewing_archive)
        self._tick_clock_display()

    def _refresh(self) -> None:
        assert self._service is not None
        family = self._service.mode.asset_family
        position: dict[int, str] = {}
        for index, piece in self._service.state.board_state.cells.items():
            if piece is None:
                continue
            key = piece_asset_key(piece, family)
            if key is not None:
                position[index] = key
        self.board.set_position(position)
        viewed_status = self._service.status()
        result_status, _result_state = _finished_result(self._service, viewed_status)
        self.status.setText(
            _status_text(
                self._service,
                viewed_status,
                vs_computer=self._vs_computer,
                human_side=self._human_side,
            )
        )
        self.status.setProperty("state", _status_state(result_status))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self._sync_clock_with_game()
        self.move_list.set_moves(
            self.service.move_log_lines,
            live_revision=self.service.record.live_revision,
            view_revision=self.service.record.view_revision,
        )
        self.live_button.setEnabled(not self.service.is_live)
        in_variation = self.service.in_variation
        self.mainline_button.setVisible(in_variation)
        self.mainline_button.setEnabled(in_variation)
        self._sync_export_controls(result_status)
        self._refresh_pocket()
        self._sync_last_move_highlight()
        self._apply_highlights(viewed_status)
        if self._maybe_auto_pass():
            return
        self._request_engine()

    def _sync_last_move_highlight(self) -> None:
        assert self._service is not None
        turn = self._service.record.turn_at(self._service.record.view_revision)
        if turn is None:
            self._last_move_squares = set()
            return
        self._last_move_squares = _action_squares(
            turn.actions, self._service.mode.board.shape.files
        )

    def _maybe_auto_pass(self) -> bool:
        if self._service is None or not self.service.is_live:
            return False
        if not self._service.mode.initial_extras.get("auto_pass"):
            return False
        if not self._human_may_move() or self.service.status() in _TERMINAL_STATUSES:
            return False
        legal = self._service._generator.generate_legal(self._service.state)
        if len(legal) != 1 or not isinstance(legal[0], PassAction):
            return False
        self._commit_side(lambda: self._service.play_action(legal[0]))
        self._refresh()
        return True

    def _hide_hands(self) -> None:
        self._hand_rail.hide()
        for pocket in (self.white_pocket, self.black_pocket):
            pocket.setVisible(False)
            pocket.clear_selection()

    def _layout_hands(self) -> None:
        layout = self._hand_rail_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(self._hand_rail)
        flipped = self.board.orientation is BoardOrientation.BLACK
        top = self.white_pocket if flipped else self.black_pocket
        bottom = self.black_pocket if flipped else self.white_pocket
        layout.addWidget(top, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addStretch()
        layout.addWidget(bottom, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

    def _refresh_pocket(self) -> None:
        assert self._service is not None
        has_drops = self._service.mode.drop_rule is not None
        if not has_drops or self._service.mode.initial_extras.get("hide_hands"):
            self._hide_hands()
            return
        types = droppable_type_names(self._service.mode)
        family = self._service.mode.asset_family
        live = (
            self.service.can_play
            and self._service.status() not in _TERMINAL_STATUSES
            and self._human_may_move()
        )
        mover = self._service.state.side_to_move
        for pocket in (self.white_pocket, self.black_pocket):
            pocket.setVisible(True)
            pocket.set_hands(
                self._service.state.hands,
                pocket.side,
                enabled=live and pocket.side is mover,
                types=types,
                asset_family=family,
                grid=True,
                flip_map=drop_flip_map(self._service.mode),
                facing_black=self.board.orientation is BoardOrientation.BLACK,
            )
        self._layout_hands()
        self._hand_rail.show()


def _duck_targets(state: GameState, move: MoveAction) -> set[int]:
    shape = state.board_state.board.shape
    source = move.from_square.index(shape.files)
    dest = move.to_square.index(shape.files)
    targets: set[int] = {source}
    for index, piece in state.board_state.cells.items():
        if index == dest:
            continue
        if piece is None or piece.side is PieceSide.NEUTRAL:
            targets.add(index)
    return targets


def _engine_squares(move_uci: str | None, files: int, ranks: int) -> set[int]:
    if not move_uci:
        return set()
    token = move_uci.split(",")[0].split("·")[0].strip()
    try:
        if "@" in token:
            square_token = token.split("@", 1)[1]
            square = parse_square(square_token, files, ranks)
            return {square.index(files)}
        action = parse_uci(normalize_engine_token(token), files=files, ranks=ranks)
        return {
            action.from_square.index(files),
            action.to_square.index(files),
        }
    except ValueError:
        return set()


def _action_squares(actions: Sequence[Action], files: int) -> set[int]:
    squares: set[int] = set()
    for action in actions:
        if isinstance(action, MoveAction):
            squares.add(action.from_square.index(files))
            squares.add(action.to_square.index(files))
        elif isinstance(action, DropAction):
            squares.add(action.to_square.index(files))
        elif isinstance(action, PlaceBlockerAction):
            squares.add(action.square.index(files))
    return squares


def _preview_squares(turn: Turn, files: int) -> tuple[int | None, int | None]:
    for action in turn.actions:
        if isinstance(action, MoveAction):
            return action.from_square.index(files), action.to_square.index(files)
        if isinstance(action, DropAction):
            return None, action.to_square.index(files)
    return None, None


def _finished_result(
    service: LocalGameService, viewed_status: GameStatus
) -> tuple[GameStatus, GameState]:
    """Keep the live game result when browsing a finished game's archive."""
    if not service.is_live:
        live_status = service.live_status()
        if live_status in _TERMINAL_STATUSES:
            return live_status, service.record.live_state()
    return viewed_status, service.state


def _status_text(
    service: LocalGameService,
    game_status: GameStatus,
    *,
    vs_computer: bool = False,
    human_side: PieceSide = PieceSide.WHITE,
) -> str:
    viewed_side = "белых" if service.state.side_to_move is PieceSide.WHITE else "чёрных"
    variation = " [ветка]" if service.in_variation else ""
    viewing = "" if service.is_live else " [архив]"
    suffix = f"{viewing}{variation}"
    if vs_computer and game_status in (GameStatus.ACTIVE, GameStatus.CHECK) and service.is_live:
        if service.state.side_to_move is not human_side:
            return f"Ход {viewed_side} — думает компьютер…"
        you = "белыми" if human_side is PieceSide.WHITE else "чёрными"
        check = " — шах" if game_status is GameStatus.CHECK else ""
        return f"Одиночная игра ({you}). Ваш ход{check}."
    result_status, result_state = _finished_result(service, game_status)
    previous = "чёрные" if result_state.side_to_move is PieceSide.WHITE else "белые"
    if result_status is GameStatus.ACTIVE:
        return f"Ход {viewed_side} — игра продолжается{suffix}"
    if result_status is GameStatus.CHECK:
        return f"Ход {viewed_side} — шах{suffix}"
    if result_status is GameStatus.CHECKMATE:
        return f"Мат. Победили {previous}.{suffix}"
    if result_status is GameStatus.STALEMATE:
        return f"Пат. Ничья.{suffix}"
    if result_status is GameStatus.REPETITION_DRAW:
        return f"Ничья: троекратное повторение позиции.{suffix}"
    if result_status is GameStatus.TRY_WIN:
        conditions = (
            service.mode.victory
            if isinstance(service.mode.victory, tuple)
            else (service.mode.victory,)
        )
        if any(getattr(item, "kind", None) is VictoryKind.OCCUPY_ZONE for item in conditions):
            return f"Победили {previous}: занят угол соперника.{suffix}"
        if any(getattr(item, "kind", None) is VictoryKind.ALIGN for item in conditions):
            from chess_core.app.game import line_winner

            winner = line_winner(service.mode, result_state)
            name = "белые" if winner is PieceSide.WHITE else "чёрные"
            return f"Победили {name}: три в ряд.{suffix}"
        return f"Победили {previous}: королевская фигура достигла зоны.{suffix}"
    if result_status is GameStatus.KING_CAPTURE_WIN:
        return f"Победили {previous}: королевская фигура взята.{suffix}"
    winner = material_winner(service.mode, result_state)
    white = sum(
        1
        for piece in result_state.board_state.cells.values()
        if piece is not None and piece.side is PieceSide.WHITE
    )
    black = sum(
        1
        for piece in result_state.board_state.cells.values()
        if piece is not None and piece.side is PieceSide.BLACK
    )
    winner_name = "белые" if winner is PieceSide.WHITE else "чёрные" if winner is PieceSide.BLACK else None
    if winner_name is None:
        return f"Ничья по материалу.{suffix}"
    if white == 0 or black == 0:
        if service.mode.initial_extras.get("empty_side_wins"):
            return f"Победили {winner_name}: не осталось фигур.{suffix}"
        return f"Победили {winner_name}: съедены все фигуры соперника.{suffix}"
    if white != black:
        return f"Победили {winner_name}: {white} — {black}.{suffix}"
    return f"Победили {winner_name}: нет легальных ходов.{suffix}"


def _status_state(game_status: GameStatus) -> str:
    if game_status is GameStatus.CHECK:
        return "check"
    if game_status is GameStatus.CHECKMATE:
        return "mate"
    if game_status is GameStatus.STALEMATE:
        return "draw"
    if game_status is GameStatus.REPETITION_DRAW:
        return "draw"
    if game_status in (
        GameStatus.MATERIAL_WIN,
        GameStatus.TRY_WIN,
        GameStatus.KING_CAPTURE_WIN,
    ):
        return "win"
    return "active"

