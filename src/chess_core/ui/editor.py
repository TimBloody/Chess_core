"""Board position editor UI."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.editor import BoardEditorService
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.modes import resolve_mode
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.piece_keys import FACING_ASSET_FAMILIES, piece_asset_key
from chess_core.ui.theme import tighten_wrapping_label
from chess_core.ui.widgets.board_widget import BoardWidget
from chess_core.ui.widgets.editor_palette import EditorPaletteStrip, PaletteToken


class EditorWidget(QWidget):
    play_requested = pyqtSignal(object)

    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = resolve_mode,
        mode_id: str = "chess",
        parent: QWidget | None = None,
        *,
        require_one_king_per_side: bool = True,
        enable_play: bool = True,
        play_button_text: str = "Играть с позиции",
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._mode_id = mode_id
        self._require_one_king_per_side = require_one_king_per_side
        self._enable_play = enable_play
        self._assets = AssetsLoader()
        self._service = BoardEditorService(
            self._resolve(mode_id),
            require_one_king_per_side=require_one_king_per_side,
        )
        self._selected_piece: tuple[str, str] | None = ("pawn", "white")
        self._eraser = False

        self.board = BoardWidget()
        self.status = QLabel()
        self.status.setObjectName("gameStatus")
        tighten_wrapping_label(self.status)
        self.fen_field = QLineEdit()
        self.white_label = QLabel("Белые")
        self.white_label.setObjectName("panelTitle")
        self.black_label = QLabel("Чёрные")
        self.black_label.setObjectName("panelTitle")
        self.white_palette = EditorPaletteStrip(assets_loader=self._assets)
        self.black_palette = EditorPaletteStrip(assets_loader=self._assets)
        self.erase_button = QPushButton("Стереть")
        self.erase_button.setCheckable(True)
        self.blocker_button = QPushButton("Блокер")
        self.blocker_button.setCheckable(True)
        self.white_to_move_button = QPushButton("Ход белых")
        self.white_to_move_button.setCheckable(True)
        self.black_to_move_button = QPushButton("Ход чёрных")
        self.black_to_move_button.setCheckable(True)
        self._side_group = QButtonGroup(self)
        self._side_group.setExclusive(True)
        self._side_group.addButton(self.white_to_move_button)
        self._side_group.addButton(self.black_to_move_button)
        self.validation = QLabel()
        tighten_wrapping_label(self.validation)

        layout = QHBoxLayout(self)
        board_col = QVBoxLayout()
        board_col.addWidget(self.status)
        board_col.addWidget(self.board, 1)
        layout.addLayout(board_col, 3)

        side_col = QVBoxLayout()
        side_col.addWidget(QLabel("Палитра"))
        side_col.addWidget(self.white_label)
        side_col.addWidget(self.white_palette)
        side_col.addWidget(self.black_label)
        side_col.addWidget(self.black_palette)
        tools = QHBoxLayout()
        tools.addWidget(self.erase_button)
        tools.addWidget(self.blocker_button)
        side_col.addLayout(tools)
        side_row = QHBoxLayout()
        side_row.addWidget(self.white_to_move_button)
        side_row.addWidget(self.black_to_move_button)
        side_col.addLayout(side_row)
        side_col.addWidget(QLabel("FEN"))
        side_col.addWidget(self.fen_field)
        for label, slot in (
            ("Стартовая", self._load_start),
            ("Очистить", self._clear),
            ("Импорт FEN", self._import_fen),
            ("Экспорт FEN", self._export_fen),
            ("Проверить", self._validate),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            side_col.addWidget(button)
        self.play_button = QPushButton(play_button_text)
        self.play_button.clicked.connect(self._play)
        self.play_button.setVisible(enable_play)
        side_col.addWidget(self.play_button)
        side_col.addWidget(self.validation)
        side_col.addStretch()
        layout.addLayout(side_col, 1)

        self.board.square_clicked.connect(self._on_square)
        self.white_palette.token_clicked.connect(self._on_palette_piece)
        self.black_palette.token_clicked.connect(self._on_palette_piece)
        self.erase_button.clicked.connect(self._select_eraser)
        self.blocker_button.clicked.connect(self._select_blocker)
        self.white_to_move_button.clicked.connect(self._set_white_to_move)
        self.black_to_move_button.clicked.connect(self._set_black_to_move)
        self._service.new_empty_position()
        self.board.set_shape(
            self._service.mode.board.shape.files,
            self._service.mode.board.shape.ranks,
        )
        self._refresh_palette()
        self._refresh_board()

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        self._service = BoardEditorService(
            self._resolve(mode_id),
            require_one_king_per_side=self._require_one_king_per_side,
        )
        self._service.load_start_position()
        self.board.set_shape(
            self._service.mode.board.shape.files,
            self._service.mode.board.shape.ranks,
        )
        self._refresh_palette()
        self._refresh_board()

    def current_state(self):
        return self._service.to_playable_state()

    def reset_empty(self) -> None:
        self._service.new_empty_position()
        self._refresh_board()

    def reload_piece_assets(self) -> None:
        self.white_palette.invalidate_renderers()
        self.black_palette.invalidate_renderers()
        self.board.update()

    def _refresh_palette(self) -> None:
        family = self._service.mode.asset_family
        facing = family in FACING_ASSET_FAMILIES
        self.white_label.setText("Готе" if facing else "Белые")
        self.black_label.setText("Сенте" if facing else "Чёрные")
        self.white_to_move_button.setText("Ход готе" if facing else "Ход белых")
        self.black_to_move_button.setText("Ход сенте" if facing else "Ход чёрных")
        self.white_palette.set_tokens(self._tokens_for(PieceSide.WHITE))
        self.black_palette.set_tokens(self._tokens_for(PieceSide.BLACK))
        self.white_palette.set_rotate_pieces(False)
        self.black_palette.set_rotate_pieces(facing)
        self._sync_palette_selection()

    def _tokens_for(self, side: PieceSide) -> tuple[PaletteToken, ...]:
        tokens: list[PaletteToken] = []
        family = self._service.mode.asset_family
        for piece_id in self._service.piece_types_for_palette():
            key = piece_asset_key(Piece(PieceTypeId(piece_id), side), family)
            if key is None:
                continue
            tokens.append(PaletteToken(piece_id, side, key))
        return tuple(tokens)

    def _on_palette_piece(self, piece_id: str, side: object) -> None:
        if not isinstance(side, PieceSide):
            return
        self._eraser = False
        self._selected_piece = (piece_id, side.name.lower())
        self.erase_button.setChecked(False)
        self.blocker_button.setChecked(False)
        self._sync_palette_selection()

    def _select_eraser(self) -> None:
        self._eraser = True
        self._selected_piece = None
        self.erase_button.setChecked(True)
        self.blocker_button.setChecked(False)
        self._sync_palette_selection()

    def _select_blocker(self) -> None:
        self._eraser = False
        self._selected_piece = ("blocker", "neutral")
        self.erase_button.setChecked(False)
        self.blocker_button.setChecked(True)
        self._sync_palette_selection()

    def _set_white_to_move(self) -> None:
        self._service.set_side_to_move(PieceSide.WHITE)
        self._refresh_board()

    def _set_black_to_move(self) -> None:
        self._service.set_side_to_move(PieceSide.BLACK)
        self._refresh_board()

    def _sync_palette_selection(self) -> None:
        if self._eraser or self._selected_piece is None:
            self.white_palette.set_selected(None, None)
            self.black_palette.set_selected(None, None)
            return
        piece_id, side_name = self._selected_piece
        if side_name == "neutral":
            self.white_palette.set_selected(None, None)
            self.black_palette.set_selected(None, None)
            return
        side = PieceSide.WHITE if side_name == "white" else PieceSide.BLACK
        self.white_palette.set_selected(piece_id, side)
        self.black_palette.set_selected(piece_id, side)

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
            key = piece_asset_key(piece, self._service.mode.asset_family)
            if key is not None:
                position[index] = key
        self.board.set_position(position)
        white = state.side_to_move is PieceSide.WHITE
        self.white_to_move_button.blockSignals(True)
        self.black_to_move_button.blockSignals(True)
        self.white_to_move_button.setChecked(white)
        self.black_to_move_button.setChecked(not white)
        self.white_to_move_button.blockSignals(False)
        self.black_to_move_button.blockSignals(False)
        side = "белых" if white else "чёрных"
        if self._service.mode.asset_family in FACING_ASSET_FAMILIES:
            side = "готе" if white else "сенте"
        self.status.setText(f"Редактор — ход {side}")
