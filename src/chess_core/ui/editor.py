"""Board position editor UI."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.editor import BoardEditorService
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.ui.widgets.board_widget import BoardWidget

_ASSET_NAMES = {
    "king": "K",
    "queen": "Q",
    "rook": "R",
    "bishop": "B",
    "knight": "N",
    "pawn": "P",
}


class EditorWidget(QWidget):
    play_requested = pyqtSignal(object)

    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        mode_id: str = "chess",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._mode_id = mode_id
        self._service = BoardEditorService(self._resolve(mode_id), require_one_king_per_side=True)
        self._selected_piece: tuple[str, str] | None = ("pawn", "white")
        self._eraser = False

        self.board = BoardWidget()
        self.status = QLabel()
        self.fen_field = QLineEdit()
        self.palette = QListWidget()
        self.validation = QLabel()

        layout = QHBoxLayout(self)
        board_col = QVBoxLayout()
        board_col.addWidget(self.status)
        board_col.addWidget(self.board)
        layout.addLayout(board_col, 3)

        side_col = QVBoxLayout()
        side_col.addWidget(QLabel("Палитра"))
        side_col.addWidget(self.palette)
        side_col.addWidget(QLabel("FEN"))
        side_col.addWidget(self.fen_field)
        for label, slot in (
            ("Стартовая", self._load_start),
            ("Очистить", self._clear),
            ("Импорт FEN", self._import_fen),
            ("Экспорт FEN", self._export_fen),
            ("Проверить", self._validate),
            ("Играть с позиции", self._play),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            side_col.addWidget(button)
        side_col.addWidget(self.validation)
        layout.addLayout(side_col, 1)

        self.board.square_clicked.connect(self._on_square)
        self.palette.currentTextChanged.connect(self._on_palette)
        self._service.new_empty_position()
        self.board.set_shape(
            self._service.mode.board.shape.files,
            self._service.mode.board.shape.ranks,
        )
        self._refresh_palette()
        self._refresh_board()

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        self._service = BoardEditorService(self._resolve(mode_id), require_one_king_per_side=True)
        self._service.load_start_position()
        self.board.set_shape(
            self._service.mode.board.shape.files,
            self._service.mode.board.shape.ranks,
        )
        self._refresh_palette()
        self._refresh_board()

    def _refresh_palette(self) -> None:
        self.palette.clear()
        self.palette.addItem("(удалить)")
        for piece_id in self._service.piece_types_for_palette():
            for side in ("white", "black"):
                self.palette.addItem(f"{piece_id}:{side}")
        self.palette.addItem("blocker:neutral")

    def _on_palette(self, text: str) -> None:
        if text == "(удалить)":
            self._eraser = True
            self._selected_piece = None
            return
        self._eraser = False
        if ":" not in text:
            return
        piece_id, side = text.split(":", 1)
        self._selected_piece = (piece_id, side)

    def _on_square(self, index: int) -> None:
        if self._eraser or self._selected_piece is None:
            self._service.remove_piece(index)
        else:
            piece_id, side = self._selected_piece
            self._service.set_piece(index, piece_id, side)
        self._refresh_board()

    def _load_start(self) -> None:
        self._service.load_start_position()
        self._refresh_board()

    def _clear(self) -> None:
        self._service.clear_board()
        self._refresh_board()

    def _import_fen(self) -> None:
        try:
            self._service.import_notation(self.fen_field.text())
            self.status.setText("FEN импортирован")
        except ValueError as exc:
            self.status.setText(str(exc))
        self._refresh_board()

    def _export_fen(self) -> None:
        try:
            self.fen_field.setText(self._service.export_notation())
        except ValueError as exc:
            self.status.setText(str(exc))

    def _validate(self) -> None:
        errors = self._service.validate_for_mode()
        self.validation.setText("\n".join(errors) if errors else "Позиция валидна")

    def _play(self) -> None:
        errors = self._service.validate_for_mode()
        if errors:
            self.validation.setText("\n".join(errors))
            return
        self.play_requested.emit(self._service.to_playable_state())

    def _refresh_board(self) -> None:
        state = self._service.state
        position: dict[int, str] = {}
        for index, piece in state.board_state.cells.items():
            if piece is None:
                continue
            if piece.side is PieceSide.NEUTRAL:
                position[index] = "wP"
                continue
            symbol = _ASSET_NAMES.get(piece.piece_type.name, piece.piece_type.name[0].upper())
            position[index] = ("w" if piece.side is PieceSide.WHITE else "b") + symbol
        self.board.set_position(position)
        side = "белых" if state.side_to_move is PieceSide.WHITE else "чёрных"
        self.status.setText(f"Редактор — ход {side}")
