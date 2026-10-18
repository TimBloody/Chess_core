import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.move import MoveAction
from chess_core.core.notation import parse_fen
from chess_core.core.piece import PieceSide, PieceTypeId
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess, giveaway
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.widgets.promotion_menu import (
    PromotionDialog,
    needs_promotion_choice,
    ordered_promotion_moves,
)


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _move(promo: str | None) -> MoveAction:
    from chess_core.core.board import Square

    choice = None if promo is None else PieceTypeId(promo)
    return MoveAction(Square(0, 6), Square(0, 7), choice)


def test_classic_promotion_menu_omits_king() -> None:
    _app()
    moves = ordered_promotion_moves([_move(name) for name in ("knight", "queen", "rook", "bishop")])
    assert [move.promotion_choice.name for move in moves] == [
        "queen",
        "rook",
        "bishop",
        "knight",
    ]
    dialog = PromotionDialog(moves, side=PieceSide.WHITE, asset_family="chess")
    assert [button.property("promotion") for button in dialog.buttons] == [
        "queen",
        "rook",
        "bishop",
        "knight",
    ]
    dialog.buttons[3].click()
    assert dialog.chosen is not None
    assert dialog.chosen.promotion_choice.name == "knight"
    dialog.close()


def test_giveaway_promotion_menu_includes_king() -> None:
    _app()
    names = ("queen", "rook", "bishop", "knight", "king")
    moves = ordered_promotion_moves([_move(name) for name in names])
    assert [move.promotion_choice.name for move in moves] == list(names)
    dialog = PromotionDialog(moves, side=PieceSide.WHITE, asset_family="chess")
    assert [button.property("promotion") for button in dialog.buttons] == list(names)
    dialog.close()


def test_single_promotion_does_not_need_a_menu() -> None:
    assert not needs_promotion_choice([_move("kingman")])
    assert needs_promotion_choice([_move("queen"), _move("knight")])


def test_local_game_uses_chosen_promotion() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(lambda _mode_id: classic_chess(), "chess", discovered=[])
    widget.load_position(parse_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", classic_chess()))
    widget._choose_promotion = lambda candidates: next(
        move
        for move in candidates
        if move.promotion_choice is not None and move.promotion_choice.name == "rook"
    )
    widget._on_square(48)
    widget._on_square(56)
    piece = widget.service.state.board_state.piece_at(56)
    assert piece is not None
    assert piece.piece_type.name == "rook"
    widget.close()


def test_giveaway_local_game_can_promote_to_king() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(lambda _mode_id: giveaway(), "giveaway", discovered=[])
    widget.load_position(parse_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", giveaway()))
    widget._choose_promotion = lambda candidates: next(
        move
        for move in candidates
        if move.promotion_choice is not None and move.promotion_choice.name == "king"
    )
    widget._on_square(48)
    widget._on_square(56)
    piece = widget.service.state.board_state.piece_at(56)
    assert piece is not None
    assert piece.piece_type.name == "king"
    widget.close()
