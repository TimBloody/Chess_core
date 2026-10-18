"""Piece drag-and-drop overlay without extra board paints on mouse move."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.widgets.board_widget import BoardWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _center(board: BoardWidget, square: int) -> QPointF:
    board_rect, cell_size = board._board_geometry()
    display = board.logical_to_display_square(square)
    file = display % board.files
    rank = display // board.files
    return QPointF(
        board_rect.left() + (file + 0.5) * cell_size,
        board_rect.top() + (board.ranks - rank - 0.5) * cell_size,
    )


def _mouse(board: BoardWidget, kind: str, pos: QPointF, button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
    global_pos = QPointF(board.mapToGlobal(pos.toPoint()))
    event = QMouseEvent(
        {
            "press": QMouseEvent.Type.MouseButtonPress,
            "move": QMouseEvent.Type.MouseMove,
            "release": QMouseEvent.Type.MouseButtonRelease,
        }[kind],
        pos,
        global_pos,
        button,
        button if kind != "release" else Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    if kind == "press":
        board.mousePressEvent(event)
    elif kind == "move":
        board.mouseMoveEvent(event)
    else:
        board.mouseReleaseEvent(event)


class _PaintBoard(BoardWidget):
    def __init__(self) -> None:
        super().__init__()
        self.paints = 0

    def paintEvent(self, event) -> None:  # noqa: ANN001
        self.paints += 1
        super().paintEvent(event)


def test_click_without_drag_emits_once() -> None:
    _app()
    board = BoardWidget()
    board.set_piece_drag_enabled(True)
    board.resize(400, 400)
    board.set_position({12: "wP"})
    clicks: list[int] = []
    board.square_clicked.connect(clicks.append)
    start = _center(board, 12)
    _mouse(board, "press", start)
    _mouse(board, "move", start + QPointF(2, 1))
    _mouse(board, "release", start)
    assert clicks == [12]
    assert not board._drag_overlay.isVisible()
    board.close()


def test_drag_uses_overlay_and_does_not_repaint_board_on_move() -> None:
    app = _app()
    board = _PaintBoard()
    board.set_piece_drag_enabled(True)
    board.resize(400, 400)
    board.set_position({12: "wP", 28: "wP"})
    board.show()
    app.processEvents()
    clicks: list[int] = []
    board.square_clicked.connect(clicks.append)
    start = _center(board, 12)
    dest = _center(board, 28)
    _mouse(board, "press", start)
    board.paints = 0
    _mouse(board, "move", start + QPointF(20, -20))
    assert board._drag_active
    assert board._drag_hidden_square == 12
    assert board._drag_overlay.isVisible()
    paints_after_start = board.paints
    _mouse(board, "move", start + QPointF(40, -40))
    _mouse(board, "move", dest)
    assert board.paints == paints_after_start
    _mouse(board, "release", dest)
    assert clicks == [12, 28]
    assert board._drag_hidden_square is None
    assert not board._drag_overlay.isVisible()
    board.close()


def test_drag_disabled_does_not_open_overlay() -> None:
    _app()
    board = BoardWidget()
    board.resize(400, 400)
    board.set_position({12: "wP"})
    start = _center(board, 12)
    _mouse(board, "press", start)
    _mouse(board, "move", start + QPointF(30, -30))
    assert not board._drag_active
    assert not board._drag_overlay.isVisible()
    board.close()


def test_local_game_drag_plays_move() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget.show()
    widget.resize(900, 640)
    QApplication.processEvents()
    board = widget.board
    assert board.piece_drag_enabled
    start = _center(board, 12)
    dest = _center(board, 28)
    _mouse(board, "press", start)
    _mouse(board, "move", start + QPointF(16, -24))
    _mouse(board, "release", dest)
    QApplication.processEvents()
    assert widget.service.state.side_to_move is PieceSide.BLACK
    assert widget.board.position.get(28) == "wP"
    assert 12 not in widget.board.position
    widget.close()
