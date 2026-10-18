"""Popup to pick a promotion piece from the legal candidates."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QWidget

from chess_core.core.move import MoveAction
from chess_core.core.piece import PieceSide
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.piece_keys import hand_piece_key

_CHESS_ORDER = ("queen", "rook", "bishop", "knight", "king")
_LABELS = {
    "queen": "Ферзь",
    "rook": "Ладья",
    "bishop": "Слон",
    "knight": "Конь",
    "king": "Король",
}


def ordered_promotion_moves(candidates: Sequence[MoveAction]) -> tuple[MoveAction, ...]:
    unique: dict[str | None, MoveAction] = {}
    for move in candidates:
        key = None if move.promotion_choice is None else move.promotion_choice.name
        unique.setdefault(key, move)

    def sort_key(name: str | None) -> tuple[int, int, str]:
        if name is None:
            return (2, 0, "")
        if name in _CHESS_ORDER:
            return (0, _CHESS_ORDER.index(name), name)
        return (1, 0, name)

    return tuple(unique[name] for name in sorted(unique, key=sort_key))


def needs_promotion_choice(candidates: Sequence[MoveAction]) -> bool:
    return len(ordered_promotion_moves(candidates)) >= 2


def choose_promotion_move(
    candidates: Sequence[MoveAction],
    *,
    parent: QWidget | None,
    side: PieceSide,
    asset_family: str,
    unpromoted_type: str | None = None,
    assets: AssetsLoader | None = None,
) -> MoveAction | None:
    """Ask for a piece when several promotions are legal; auto-pick a single option."""
    ordered = ordered_promotion_moves(candidates)
    if not ordered:
        return None
    if not needs_promotion_choice(candidates):
        return ordered[0]
    dialog = PromotionDialog(
        ordered,
        side=side,
        asset_family=asset_family,
        unpromoted_type=unpromoted_type,
        assets=assets,
        parent=parent,
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.chosen
    return None


class PromotionDialog(QDialog):
    """One button per legal promotion (and the unpromoted face, if allowed)."""

    def __init__(
        self,
        moves: Sequence[MoveAction],
        *,
        side: PieceSide,
        asset_family: str,
        unpromoted_type: str | None = None,
        assets: AssetsLoader | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chosen: MoveAction | None = None
        self.buttons: list[QPushButton] = []
        self.setWindowTitle("Превращение")
        self.setModal(True)
        self.setStyleSheet(
            "QPushButton#promotionChoice { min-width: 56px; min-height: 56px; padding: 6px; }"
        )
        loader = assets or AssetsLoader()
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 10, 10)
        for move in moves:
            type_name = (
                unpromoted_type
                if move.promotion_choice is None
                else move.promotion_choice.name
            )
            button = QPushButton()
            button.setObjectName("promotionChoice")
            button.setProperty("promotion", type_name or "")
            button.setToolTip(_LABELS.get(type_name or "", type_name or "Оставить"))
            button.setIconSize(QSize(48, 48))
            icon = _piece_icon(loader, type_name or "pawn", side, asset_family)
            if icon is not None:
                button.setIcon(icon)
            else:
                button.setText(button.toolTip())
            button.clicked.connect(lambda _checked=False, picked=move: self._pick(picked))
            row.addWidget(button)
            self.buttons.append(button)

    def _pick(self, move: MoveAction) -> None:
        self.chosen = move
        self.accept()


def _piece_icon(
    assets: AssetsLoader,
    type_name: str,
    side: PieceSide,
    asset_family: str,
    size: int = 48,
) -> QIcon | None:
    key = hand_piece_key(type_name, side, asset_family)
    if key is None:
        return None
    try:
        path = str(assets.piece_path(key))
    except FileNotFoundError:
        return None
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
