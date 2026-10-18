"""Offscreen lobby smoke."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.branches.server_play import ServerPlayWindow
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.network_game import NetworkGameWidget
from chess_core.ui.widgets.board_widget import BoardWidget
from chess_core.ui.widgets.match_lobby import MatchLobbyWidget


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_network_page_is_in_shell() -> None:
    _app()
    register_builtin_modes()
    window = ServerPlayWindow(default_registry.list_modes(), UiSession("chess"))
    assert isinstance(window._network_game, NetworkGameWidget)
    assert isinstance(window._network_game.lobby, MatchLobbyWidget)
    assert window._network_game.move_list is not None
    window.close()


def test_hand_and_brain_type_highlights() -> None:
    _app()
    board = BoardWidget()
    board.set_shape(8, 8)
    board.set_highlights(type_highlights={1, 6}, blocked_squares={4})
    assert 1 in board._type_highlights
    assert 4 in board._blocked_squares
