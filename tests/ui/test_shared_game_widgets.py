"""Tests for shared game widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.app.clock import GameClockService
from chess_core.app.engine import EngineEvaluation
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import HandsState
from chess_core.core.time_control import TimeControlConfig
from chess_core.modes import register_builtin_modes
from chess_core.modes.shogi import dobutsu_shogi
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.piece_keys import piece_asset_key
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_move_list_emits_revision() -> None:
    _app()
    widget = MoveListWidget()
    widget.set_moves(["1. e4  e5"], live_revision=1, view_revision=1)
    assert widget.count() == 1


def test_clock_widget_formats_snapshot() -> None:
    _app()
    widget = GameClockWidget()
    service = GameClockService(TimeControlConfig.sudden_death(5), _Clock())
    widget.set_snapshot(service.snapshot())
    assert ":" in widget._white.text()
    style = widget.black_clock.styleSheet().lower()
    assert "#f5f5f5" in style
    assert "playerclockwidget qlabel" in style


def test_evaluation_bar_shows_cp() -> None:
    _app()
    widget = EvaluationBarWidget()
    widget.set_evaluation(EngineEvaluation(score_cp=35, mate_in=None, pv=("e2e4",)))
    assert "+0.3" in widget._bar.text()


def test_pocket_omits_zero_counts_and_shows_only_owned_types() -> None:
    _app()
    hands = HandsState()
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("silver"), PieceSide.WHITE))
    widget = PocketWidget(PieceSide.WHITE)
    widget.set_hands(
        hands,
        PieceSide.WHITE,
        types=("pawn", "lance", "knight", "silver", "gold", "bishop", "rook"),
        asset_family="shogi",
        grid=True,
    )
    assert widget.visible_types == ("pawn", "silver")
    assert widget.is_grid
    assert widget._stacks[0].count == 2
    assert widget._stacks[0].piece_key == "0FU"


def test_dobutsu_piece_keys_use_animal_svgs() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    white_lion = state.board_state.piece_at(1)
    black_lion = state.board_state.piece_at(10)
    white_key = piece_asset_key(white_lion, mode.asset_family)
    black_key = piece_asset_key(black_lion, mode.asset_family)
    assert white_key == "dobutsu/lion@w"
    assert black_key == "dobutsu/lion@b"
    assets = AssetsLoader()
    assert assets.piece_path(white_key).name == "lion.svg"
    assert assets.piece_path("dobutsu/chick@w").name == "chick.svg"
    assert assets.piece_path("dobutsu/giraffe@b").name == "giraffe.svg"


def test_dobutsu_local_game_does_not_use_chess_piece_keys() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "dobutsu_shogi")
    assert widget.board.position[1] == "dobutsu/lion@w"
    assert widget.board.position[10] == "dobutsu/lion@b"
    assert widget.board.position[4] == "dobutsu/chick@w"
    assert widget.white_pocket.is_grid
    widget.close()


class _Clock:
    def now_ms(self) -> int:
        return 0
