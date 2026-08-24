"""Thin PyQt adapter for Lichess puzzle solving."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.game import GameStatus
from chess_core.app.puzzles import PuzzleJudgement, PuzzleSession
from chess_core.core.move import MoveAction
from chess_core.core.piece import PieceSide
from chess_core.infra.storage.lichess_puzzles import load_lichess_puzzles
from chess_core.modes.chess import classic_chess
from chess_core.ui.piece_keys import piece_asset_key
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget

_THEME_LABELS = {
    "mate": "мат",
    "mateIn1": "мат в 1",
    "mateIn2": "мат в 2",
    "mateIn3": "мат в 3",
    "fork": "вилка",
    "pin": "связка",
    "skewer": "сквозной удар",
    "discoveredAttack": "вскрытое нападение",
    "hangingPiece": "висячая фигура",
    "sacrifice": "жертва",
    "backRankMate": "мат на последней горизонтали",
    "endgame": "эндшпиль",
    "opening": "дебют",
    "middlegame": "миттельшпиль",
    "crushing": "решающее преимущество",
    "advantage": "преимущество",
    "oneMove": "один ход",
    "short": "короткая",
    "long": "длинная",
    "attraction": "завлечение",
    "deflection": "отвлечение",
    "quietMove": "тихий ход",
    "exposedKing": "оголённый король",
    "advancedPawn": "проходная",
    "trappedPiece": "пойманная фигура",
    "doubleCheck": "двойной шах",
    "capturingDefender": "уничтожение защитника",
    "kingsideAttack": "атака на короля",
    "pawnEndgame": "пешечный эндшпиль",
    "master": "мастерская партия",
}

_REVEAL_MS = 2000
_SOLVED_MS = 1200


class PuzzleWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session: PuzzleSession | None = None
        self._all_puzzles: tuple = ()
        self._selected: int | None = None
        self._locked = False
        self._hint_move = None
        self.board = BoardWidget()
        self.status = QLabel()
        self.status.setObjectName("gameStatus")
        self.status.setWordWrap(True)
        self.feedback = QLabel()
        self.feedback.setObjectName("gameHint")
        self.feedback.setWordWrap(True)
        self.instructions = QLabel(
            "Найдите лучший ход. Подсказка подсвечивает фигуру. "
            "Неверный ход показывает решение. F — перевернуть доску."
        )
        self.instructions.setWordWrap(True)
        self.rating_combo = QComboBox()
        self.rating_combo.addItem("Все рейтинги", None)
        self.rating_combo.addItem("До 1200", (0, 1200))
        self.rating_combo.addItem("1200–1800", (1200, 1800))
        self.rating_combo.addItem("1800+", (1800, 4000))
        self.prev_button = QPushButton("Предыдущая")
        self.next_button = QPushButton("Следующая")
        self.retry_button = QPushButton("Эта же задача")
        self.hint_button = QPushButton("Подсказка")

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.feedback)
        layout.addWidget(self.board, 1)
        layout.addWidget(self.instructions)
        controls = QHBoxLayout()
        controls.addWidget(self.rating_combo)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.retry_button)
        controls.addWidget(self.hint_button)
        controls.addStretch()
        layout.addLayout(controls)

        self.board.square_clicked.connect(self._on_square)
        self.prev_button.clicked.connect(self._go_prev)
        self.next_button.clicked.connect(self._go_next)
        self.retry_button.clicked.connect(self._reload_current)
        self.hint_button.clicked.connect(self._show_hint)
        self.rating_combo.currentIndexChanged.connect(self._apply_rating_filter)
        self._flip_shortcut = QShortcut(QKeySequence("F"), self)
        self._flip_shortcut.activated.connect(self.board.flip_orientation)
        self._advance_timer = QTimer(self)
        self._advance_timer.setSingleShot(True)
        self._advance_timer.timeout.connect(self._go_next)

        self._load_catalog()

    @property
    def session(self) -> PuzzleSession:
        if self._session is None:
            raise RuntimeError("Puzzle catalog is not loaded")
        return self._session

    def _load_catalog(self) -> None:
        try:
            puzzles = load_lichess_puzzles()
        except FileNotFoundError:
            self.status.setText("Набор задач Lichess не найден.")
            self.feedback.setText("")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.hint_button.setEnabled(False)
            return
        if not puzzles:
            self.status.setText("Набор задач Lichess пуст.")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.hint_button.setEnabled(False)
            return
        self._all_puzzles = tuple(puzzles)
        self._session = PuzzleSession(classic_chess(), puzzles)
        self.board.set_shape(8, 8)
        self._show_current("Найдите ход.")

    def _reload_current(self) -> None:
        if self._session is None:
            return
        self._advance_timer.stop()
        self._session.load_index(self._session.index)
        self._show_current("Найдите ход.")

    def _go_next(self) -> None:
        if self._session is None:
            return
        self._advance_timer.stop()
        self._session.next_puzzle()
        self._show_current("Найдите ход.")

    def _go_prev(self) -> None:
        if self._session is None:
            return
        self._advance_timer.stop()
        self._session.previous_puzzle()
        self._show_current("Найдите ход.")

    def _show_hint(self) -> None:
        if self._session is None or self._locked:
            return
        move = self._session.hint_action()
        if move is None:
            self.feedback.setText("Подсказки больше нет.")
            return
        self._hint_move = move
        self.feedback.setText("Подсказка: походите подсвеченной фигурой.")
        self._refresh()

    def _apply_rating_filter(self) -> None:
        if not self._all_puzzles:
            return
        bounds = self.rating_combo.currentData()
        if bounds is None:
            filtered = list(self._all_puzzles)
        else:
            low, high = bounds
            filtered = [
                puzzle
                for puzzle in self._all_puzzles
                if low <= puzzle.rating < high
            ]
        if not filtered:
            self.status.setText("В этом диапазоне задач нет. Выберите другой рейтинг.")
            return
        current_id = self._session.puzzle.puzzle_id if self._session is not None else ""
        self._session = PuzzleSession(classic_chess(), filtered)
        for index, puzzle in enumerate(filtered):
            if puzzle.puzzle_id == current_id:
                self._session.load_index(index)
                break
        self._show_current("Найдите ход.")

    def _show_current(self, message: str) -> None:
        self._locked = False
        self._selected = None
        self._hint_move = None
        self.session.game.clear_selection()
        side = self.session.solver_side
        self.board.set_orientation(
            BoardOrientation.WHITE if side is PieceSide.WHITE else BoardOrientation.BLACK
        )
        self.feedback.setText(message)
        self._refresh()

    def _on_square(self, index: int) -> None:
        if self._session is None or self._locked:
            return
        game = self.session.game
        piece = game.state.board_state.piece_at(index)
        if self._selected is None or (
            piece is not None and piece.side is game.state.side_to_move
        ):
            if piece is not None and piece.side is game.state.side_to_move:
                self._selected = index
                game.legal_moves_for_square(index)
                self._refresh()
            return

        remaining = [
            move
            for move in game.selected_moves
            if move.to_square.index(game.mode.board.shape.files) == index
        ]
        if not remaining:
            if piece is not None and piece.side is game.state.side_to_move:
                self._selected = index
                game.legal_moves_for_square(index)
                self._refresh()
                return
            game.clear_selection()
            self._selected = None
            self._refresh()
            return
        self._apply_attempt(_prefer_queen_promotion(remaining))

    def _apply_attempt(self, move: MoveAction) -> None:
        result = self.session.attempt(move)
        self._selected = None
        self._hint_move = None
        self.session.game.clear_selection()
        if result.judgement is PuzzleJudgement.ILLEGAL:
            self._refresh()
            return
        if result.judgement is PuzzleJudgement.WRONG:
            self._locked = True
            self.session.play_expected()
            self.feedback.setText(
                f"Неверно. Правильный ход: {result.notation or 'см. доску'}."
            )
            self._refresh(reveal=result.expected)
            self._advance_timer.start(_REVEAL_MS)
            return
        if result.judgement is PuzzleJudgement.SOLVED:
            self._locked = True
            self.feedback.setText("Решено!")
            self._refresh()
            self._advance_timer.start(_SOLVED_MS)
            return
        self.feedback.setText("Верно, продолжайте.")
        self._refresh()

    def _refresh(self, *, reveal: MoveAction | None = None) -> None:
        if self._session is None:
            return
        game = self.session.game
        position: dict[int, str] = {}
        for index, piece in game.state.board_state.cells.items():
            if piece is None:
                continue
            key = piece_asset_key(piece, game.mode.asset_family)
            if key is not None:
                position[index] = key
        self.board.set_position(position)

        puzzle = self.session.puzzle
        side = "белых" if game.state.side_to_move is PieceSide.WHITE else "чёрных"
        themes = ", ".join(
            _THEME_LABELS.get(theme, theme) for theme in puzzle.themes[:4]
        )
        rating = f"{puzzle.rating}" if puzzle.rating else "?"
        ply, total = self.session.player_progress
        self.status.setText(
            f"Задача {self.session.index + 1}/{self.session.total} · {puzzle.puzzle_id} · "
            f"{rating} · ход {side} · {ply}/{total}"
            + (f" · {themes}" if themes else "")
        )

        files = game.mode.board.shape.files
        selected = self._selected
        legal: set[int] = set()
        check: set[int] = set()
        engine: set[int] = set()
        last_move: set[int] = set()
        last = self.session.hint_move
        if last is not None:
            last_move = {last.from_square.index(files), last.to_square.index(files)}
        if reveal is not None:
            selected = reveal.from_square.index(files)
            legal = {reveal.to_square.index(files)}
        elif self._hint_move is not None:
            engine = {
                self._hint_move.from_square.index(files),
                self._hint_move.to_square.index(files),
            }
            selected = self._hint_move.from_square.index(files)
        elif selected is not None:
            legal = {
                move.to_square.index(files)
                for move in game.selected_moves
            }
        status = game.status()
        if status in (GameStatus.CHECK, GameStatus.CHECKMATE):
            for index, piece in game.state.board_state.cells.items():
                if (
                    piece is not None
                    and piece.side is game.state.side_to_move
                    and piece.piece_type.name == game.mode.royal_type
                ):
                    check.add(index)
        self.board.set_highlights(
            selected=selected,
            legal_destinations=legal,
            check_squares=check,
            last_move_squares=last_move,
            engine_squares=engine,
        )


def _prefer_queen_promotion(candidates: list[MoveAction]) -> MoveAction:
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.promotion_choice is not None
            and candidate.promotion_choice.name == "queen"
        ),
        candidates[0],
    )
