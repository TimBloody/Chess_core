"""Board position editor UI."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.editor import BoardEditorService
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.core.turn import StepKind
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.piece_assets import FACING_ASSET_FAMILIES, piece_svg_key, piece_svg_key_for
from chess_core.ui.widgets.board_widget import BoardOrientation, BoardWidget
from chess_core.ui.widgets.editor_palette import EditorPaletteStrip, PaletteToken


class EditorTool(Enum):
    PLACE = auto()
    MOVE = auto()
    ERASE = auto()


def _side_caption(mode: GameMode, side: PieceSide) -> str:
    if mode.asset_family in FACING_ASSET_FAMILIES:
        return "Сенте" if side is PieceSide.BLACK else "Готе"
    return "Белые" if side is PieceSide.WHITE else "Чёрные"


def _side_name(side: PieceSide) -> str:
    if side is PieceSide.NEUTRAL:
        return "neutral"
    return side.name.lower()


class EditorWidget(QWidget):
    play_requested = pyqtSignal(object)

    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode] = default_registry.get,
        mode_id: str = "chess",
        parent: QWidget | None = None,
        *,
        require_one_king_per_side: bool = True,
        enable_play: bool = True,
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
        self._tool = EditorTool.PLACE
        self._selected_piece: tuple[str, PieceSide] | None = None
        self._lifted: tuple[int, str, PieceSide] | None = None

        self.board = BoardWidget()
        self.status = QLabel()
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.fen_field = QLineEdit()
        self.fen_label = QLabel("FEN / SFEN")
        self.validation = QLabel()
        self.validation.setWordWrap(True)
        self.top_label = QLabel()
        self.bottom_label = QLabel()
        self.top_palette = EditorPaletteStrip(assets_loader=self._assets)
        self.bottom_palette = EditorPaletteStrip(assets_loader=self._assets)
        self.side_combo = QComboBox()
        self.place_button = QToolButton()
        self.move_button = QToolButton()
        self.erase_button = QToolButton()

        layout = QHBoxLayout(self)
        board_col = QVBoxLayout()
        board_col.addWidget(self.status)
        board_col.addWidget(self.board, 1)
        board_col.addWidget(self.hint)
        layout.addLayout(board_col, 3)

        palette_host = QWidget()
        palette_layout = QVBoxLayout(palette_host)
        palette_layout.setContentsMargins(0, 0, 0, 0)
        palette_layout.addWidget(self.top_label)
        palette_layout.addWidget(self.top_palette)
        palette_layout.addWidget(self.bottom_label)
        palette_layout.addWidget(self.bottom_palette)
        palette_layout.addStretch()
        palette_scroll = QScrollArea()
        palette_scroll.setWidgetResizable(True)
        palette_scroll.setWidget(palette_host)
        palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        side_col = QVBoxLayout()
        side_col.addWidget(QLabel("Инструменты"))
        side_col.addLayout(self._build_tools())
        side_col.addWidget(QLabel("Чья очередь хода"))
        side_col.addWidget(self.side_combo)
        side_col.addWidget(palette_scroll, 1)
        side_col.addWidget(self.fen_label)
        side_col.addWidget(self.fen_field)
        for label, slot in (
            ("Стартовая позиция", self._load_start),
            ("Очистить доску", self._clear),
            ("Импорт записи", self._import_fen),
            ("Экспорт записи", self._export_fen),
            ("Проверить позицию", self._validate),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            side_col.addWidget(button)
        self.play_button = QPushButton("Играть с позиции")
        self.play_button.clicked.connect(self._play)
        self.play_button.setVisible(enable_play)
        side_col.addWidget(self.play_button)
        side_col.addWidget(self.validation)
        layout.addLayout(side_col, 1)

        self.board.square_clicked.connect(self._on_square)
        self.board.square_right_clicked.connect(self._erase_square)
        self.top_palette.token_clicked.connect(self._on_palette_piece)
        self.bottom_palette.token_clicked.connect(self._on_palette_piece)
        self.side_combo.currentIndexChanged.connect(self._on_side_changed)
        self._service.new_empty_position()
        self._apply_mode_presentation()
        self._refresh_palette()
        self._refresh_board()
        self.board.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build_tools(self) -> QHBoxLayout:
        group = QButtonGroup(self)
        group.setExclusive(True)
        layout = QHBoxLayout()
        specs = (
            (self.place_button, "Ставить", EditorTool.PLACE, None),
            (self.move_button, "Переместить", EditorTool.MOVE, "move"),
            (self.erase_button, "Стереть", EditorTool.ERASE, "eraser"),
        )
        for button, label, tool, icon_name in specs:
            button.setText(label)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            if icon_name:
                button.setIcon(QIcon(str(self._assets.ui_icon_path(icon_name))))
                button.setIconSize(QSize(28, 28))
            button.clicked.connect(lambda _checked=False, chosen=tool: self._set_tool(chosen))
            group.addButton(button)
            layout.addWidget(button)
        self.place_button.setChecked(True)
        self.place_button.setToolTip("Выберите фигуру в палитре и нажмите клетку")
        self.move_button.setToolTip("Снимите фигуру с доски и поставьте на другую клетку")
        self.erase_button.setToolTip("Нажмите клетку, чтобы убрать фигуру. ПКМ делает то же самое")
        return layout

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        self._cancel_lift()
        self._service = BoardEditorService(
            self._resolve(mode_id),
            require_one_king_per_side=self._require_one_king_per_side,
        )
        self._service.load_start_position()
        self._apply_mode_presentation()
        self._refresh_palette()
        self._refresh_board()

    def current_state(self):
        return self._service.to_playable_state()

    def reset_empty(self) -> None:
        self._cancel_lift()
        self._service.new_empty_position()
        self._refresh_board()

    def load_from_state(self, state) -> None:
        self._cancel_lift()
        self._service.load_state(state)
        self._apply_mode_presentation()
        self._refresh_board()

    def _apply_mode_presentation(self) -> None:
        mode = self._service.mode
        self.board.set_shape(mode.board.shape.files, mode.board.shape.ranks)
        self.board.set_facing_opponent(mode.facing_opponent)
        self.board.set_orientation(
            BoardOrientation.BLACK
            if mode.default_view_side is PieceSide.BLACK
            else BoardOrientation.WHITE
        )
        self.fen_label.setText("SFEN" if mode.drop_rule is not None else "FEN")
        self.side_combo.blockSignals(True)
        self.side_combo.clear()
        for side in (mode.starting_side, mode.starting_side.opponent()):
            self.side_combo.addItem(_side_caption(mode, side), side)
        self.side_combo.blockSignals(False)

    def _refresh_palette(self) -> None:
        mode = self._service.mode
        bottom = mode.default_view_side
        top = bottom.opponent()
        self.top_label.setText(_side_caption(mode, top))
        self.bottom_label.setText(_side_caption(mode, bottom))
        self.top_palette.set_tokens(self._tokens_for_side(top))
        self.bottom_palette.set_tokens(self._tokens_for_side(bottom))
        self.top_palette.set_rotate_pieces(bool(mode.facing_opponent))
        self.bottom_palette.set_rotate_pieces(False)
        self._select_default_piece()
        self._sync_palette_selection()

    def _tokens_for_side(self, side: PieceSide) -> tuple[PaletteToken, ...]:
        mode = self._service.mode
        bases: list[str] = []
        promoted: list[str] = []
        for piece_type in mode.pieces.all_types():
            name = piece_type.id.name
            if piece_type.demotes_to:
                promoted.append(name)
            else:
                bases.append(name)
        tokens = [
            PaletteToken(name, side, piece_svg_key_for(mode, name, side))
            for name in (*bases, *promoted)
        ]
        if self._mode_has_blocker() and side is mode.default_view_side:
            tokens.append(PaletteToken("blocker", PieceSide.NEUTRAL, "duck"))
        return tuple(tokens)

    def _mode_has_blocker(self) -> bool:
        return any(
            step.kind is StepKind.PLACE_BLOCKER
            for step in self._service.mode.turn_scenario.steps
        )

    def _select_default_piece(self) -> None:
        tokens = self.bottom_palette.tokens or self.top_palette.tokens
        preferred = next(
            (token for token in tokens if token.piece_id in {"pawn", "chick"}),
            None,
        )
        if preferred is None:
            preferred = next(
                (
                    token
                    for token in tokens
                    if token.piece_id != "blocker"
                ),
                tokens[0] if tokens else None,
            )
        self._selected_piece = (
            None if preferred is None else (preferred.piece_id, preferred.side)
        )

    def _sync_palette_selection(self) -> None:
        piece_id, side = self._selected_piece or (None, None)
        self.top_palette.set_selected(piece_id, side)
        self.bottom_palette.set_selected(piece_id, side)

    def _set_tool(self, tool: EditorTool) -> None:
        if tool is not EditorTool.MOVE:
            self._cancel_lift()
        self._tool = tool
        self.place_button.setChecked(tool is EditorTool.PLACE)
        self.move_button.setChecked(tool is EditorTool.MOVE)
        self.erase_button.setChecked(tool is EditorTool.ERASE)
        self.board.setCursor(
            {
                EditorTool.PLACE: Qt.CursorShape.PointingHandCursor,
                EditorTool.MOVE: Qt.CursorShape.OpenHandCursor,
                EditorTool.ERASE: Qt.CursorShape.CrossCursor,
            }[tool]
        )
        self._refresh_board()

    def _on_palette_piece(self, piece_id: str, side: object) -> None:
        if not isinstance(side, PieceSide):
            return
        self._selected_piece = (piece_id, side)
        self._sync_palette_selection()
        self._set_tool(EditorTool.PLACE)

    def _on_side_changed(self, index: int) -> None:
        side = self.side_combo.itemData(index)
        if isinstance(side, PieceSide):
            self._service.set_side_to_move(side)
            self._refresh_status()

    def _on_square(self, index: int) -> None:
        if self._tool is EditorTool.ERASE:
            self._erase_square(index)
            return
        if self._tool is EditorTool.MOVE:
            self._move_on_square(index)
            return
        if self._selected_piece is None:
            self.status.setText("Сначала выберите фигуру в палитре.")
            return
        piece_id, side = self._selected_piece
        self._service.set_piece(index, piece_id, _side_name(side))
        self._refresh_board()

    def _move_on_square(self, index: int) -> None:
        occupant = self._service.state.board_state.piece_at(index)
        if self._lifted is None:
            if occupant is None:
                self.status.setText("Выберите фигуру на доске, которую нужно переместить.")
                return
            self._lifted = (index, occupant.piece_type.name, occupant.side)
            self._service.remove_piece(index)
            self._refresh_board()
            return
        origin, piece_id, side = self._lifted
        self._lifted = None
        self._service.set_piece(index, piece_id, _side_name(side))
        if index != origin and occupant is not None:
            self._service.set_piece(origin, occupant.piece_type.name, _side_name(occupant.side))
        self._refresh_board()

    def _erase_square(self, index: int) -> None:
        if self._lifted is not None and self._lifted[0] == index:
            self._lifted = None
        self._service.remove_piece(index)
        self._refresh_board()

    def _cancel_lift(self) -> None:
        if self._lifted is None:
            return
        index, piece_id, side = self._lifted
        self._service.set_piece(index, piece_id, _side_name(side))
        self._lifted = None

    def _load_start(self) -> None:
        self._cancel_lift()
        self._service.load_start_position()
        self._sync_side_combo()
        self._refresh_board()

    def _clear(self) -> None:
        self._cancel_lift()
        self._service.clear_board()
        self._refresh_board()

    def _import_fen(self) -> None:
        try:
            self._service.import_notation(self.fen_field.text())
            self.status.setText("Запись импортирована")
            self._sync_side_combo()
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
        self.validation.setText(
            "\n".join(self._translate_errors(errors)) if errors else "Позиция валидна"
        )

    def _play(self) -> None:
        self._cancel_lift()
        errors = self._service.validate_for_mode()
        if errors:
            self.validation.setText("\n".join(self._translate_errors(errors)))
            return
        self.play_requested.emit(self._service.to_playable_state())

    def _translate_errors(self, errors: list[str]) -> list[str]:
        translated = []
        for error in errors:
            if "royal piece" in error and "white" in error:
                translated.append("Нужна ровно одна королевская фигура белых/готе.")
            elif "royal piece" in error and "black" in error:
                translated.append("Нужна ровно одна королевская фигура чёрных/сенте.")
            else:
                translated.append(error)
        return translated

    def _sync_side_combo(self) -> None:
        side = self._service.state.side_to_move
        index = self.side_combo.findData(side)
        if index >= 0:
            self.side_combo.blockSignals(True)
            self.side_combo.setCurrentIndex(index)
            self.side_combo.blockSignals(False)

    def _refresh_board(self) -> None:
        state = self._service.state
        position: dict[int, str] = {}
        for index, piece in state.board_state.cells.items():
            if piece is None:
                continue
            position[index] = piece_svg_key(self._service.mode, piece)
        self.board.set_position(position)
        self.board.set_highlights(
            selected=None if self._lifted is None else self._lifted[0]
        )
        self._sync_side_combo()
        self._refresh_status()

    def _refresh_status(self) -> None:
        state = self._service.state
        side = _side_caption(self._service.mode, state.side_to_move)
        tool = {
            EditorTool.PLACE: "постановка фигуры",
            EditorTool.MOVE: "перемещение",
            EditorTool.ERASE: "стирание",
        }[self._tool]
        extra = ""
        if self._tool is EditorTool.PLACE and self._selected_piece is not None:
            extra = f" · выбрано: {self._selected_piece[0]}"
        elif self._lifted is not None:
            extra = " · фигура снята, нажмите клетку назначения"
        self.status.setText(f"Редактор — ход {side} — {tool}{extra}")
        self.hint.setText(
            "Выберите фигуру в палитре и нажмите клетку. "
            "Правый клик стирает. «Переместить» снимает фигуру с доски "
            "и ставит на другую клетку."
        )

    def reload_piece_assets(self) -> None:
        self.board.invalidate_piece_renderers()
        self.top_palette.invalidate_renderers()
        self.bottom_palette.invalidate_renderers()
        self._refresh_board()
