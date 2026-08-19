"""Offscreen UI contracts for abstract board games."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.main_window import MainWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.piece_assets import piece_svg_key

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_boardgame_assets_resolve() -> None:
    assets = AssetsLoader()
    for key in (
        "wstone",
        "bstone",
        "wreversi_disc",
        "breversi_disc",
        "wcorner",
        "bcorner",
        "wgobblet_small",
        "bgobblet_large",
    ):
        assert assets.piece_path(key).is_file()
    assert piece_svg_key(Piece(PieceTypeId("stone"), PieceSide.BLACK)) == "bstone"
    assert (
        piece_svg_key(Piece(PieceTypeId("gobblet_medium"), PieceSide.WHITE))
        == "wgobblet_medium"
    )


def test_gomoku_click_places_a_stone() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "gomoku")
    assert widget.board.files == 15
    assert widget.board.position == {}
    widget.board.square_clicked.emit(112)
    assert widget.board.position[112] == "bstone"
    assert widget.service.state.side_to_move is PieceSide.WHITE
    widget.close()


def test_reversi_start_and_legal_click() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "reversi")
    assert widget.board.files == 8
    assert widget.board.position[27] == "wreversi_disc"
    widget.board.square_clicked.emit(26)  # c4
    assert widget.board.position[26] == "breversi_disc"
    assert widget.board.position[27] == "breversi_disc"
    widget.close()


def test_corners_and_gobblet_modes_load() -> None:
    _app()
    register_builtin_modes()
    window = MainWindow(default_registry.list_modes(), UiSession("corners"))
    window.show()
    assert window._local_game is not None
    assert len(window._local_game.board.position) == 24
    window._local_game.set_mode("corners+3x3")
    assert len(window._local_game.board.position) == 18
    window._local_game.set_mode("gobblet")
    assert window._local_game.board.files == 3
    assert window._local_game.board.position == {}
    assert not window._local_game.reserve_panel.isVisible()
    assert window._local_game.white_pocket.isVisible()
    assert window._local_game.black_pocket.isVisible()
    assert window._local_game.white_pocket.is_grid
    assert not window._local_game._hand_rail.isHidden()
    window.close()


def test_gobblet_reserve_place_and_win_status() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "gobblet")
    widget.show()
    assert widget.white_pocket.isVisible()
    assert widget.white_pocket.is_grid
    widget.white_pocket.piece_clicked.emit("gobblet_small")
    widget.board.square_clicked.emit(0)
    assert widget.board.position[0] == "wgobblet_small"
    assert widget.service.state.side_to_move is PieceSide.BLACK
    widget.close()


def test_gobblet_relocate_click_moves_and_uncovers() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "gobblet+relocate")
    widget.show()
    widget.white_pocket.piece_clicked.emit("gobblet_small")
    widget.board.square_clicked.emit(0)
    widget.black_pocket.piece_clicked.emit("gobblet_medium")
    widget.board.square_clicked.emit(0)
    widget.white_pocket.piece_clicked.emit("gobblet_small")
    widget.board.square_clicked.emit(4)
    assert widget.board.position[0] == "bgobblet_medium"
    widget.board.square_clicked.emit(0)
    widget.board.square_clicked.emit(8)
    assert widget.board.position[8] == "bgobblet_medium"
    assert widget.board.position[0] == "wgobblet_small"
    widget.close()
