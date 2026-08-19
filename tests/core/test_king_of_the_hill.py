"""King of the Hill mode contracts."""

from chess_core.app.game import GameStatus, LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryKind
from chess_core.modes.chess import king_of_the_hill
from chess_core.modes.koth_rules import center_zone_mask
from chess_core.modes.shogi import dobutsu_shogi


def _piece(name: str, side: PieceSide) -> Piece:
    return Piece(PieceTypeId(name), side)


def _clear(state, cells: dict[int, Piece], side: PieceSide) -> None:
    state.board_state.cells = {
        index: cells.get(index) for index in range(state.board_state.board.shape.cell_count)
    }
    state.side_to_move = side


def test_king_of_the_hill_start_has_twenty_legal_moves() -> None:
    mode = king_of_the_hill()
    state = mode.initial_state()
    assert not mode.is_dummy
    assert mode.modifier_ids == ("king_of_the_hill",)
    assert VictoryKind.KING_REACHES_ZONE in mode.victory_kinds()
    mask = next(
        condition.target_zone_mask
        for condition in mode.victory_conditions()
        if condition.kind is VictoryKind.KING_REACHES_ZONE
    )
    assert mask == center_zone_mask(files=8, ranks=8)
    assert len(MoveGenerator(mode).generate_legal(state)) == 20


def test_king_of_the_hill_safe_centre_wins_for_previous_side() -> None:
    mode = king_of_the_hill()
    state = mode.initial_state()
    _clear(
        state,
        {
            28: _piece("king", PieceSide.WHITE),
            4: _piece("king", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    game = LocalGameService(mode, initial_state=state)
    assert game.status() is GameStatus.VARIANT_WIN


def test_king_of_the_hill_attacked_centre_does_not_win() -> None:
    mode = king_of_the_hill()
    state = mode.initial_state()
    _clear(
        state,
        {
            28: _piece("king", PieceSide.WHITE),
            52: _piece("queen", PieceSide.BLACK),
            0: _piece("king", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    game = LocalGameService(mode, initial_state=state)
    assert game.status() is not GameStatus.VARIANT_WIN


def test_dobutsu_last_rank_try_still_wins_without_zone_mask() -> None:
    mode = dobutsu_shogi()
    try_state = mode.initial_state()
    _clear(
        try_state,
        {
            0: _piece("giraffe", PieceSide.WHITE),
            2: _piece("lion", PieceSide.WHITE),
            4: _piece("lion", PieceSide.BLACK),
        },
        PieceSide.BLACK,
    )
    game = LocalGameService(mode, initial_state=try_state)
    game.play(MoveAction(Square(1, 1), Square(0, 0)))
    assert game.status() is GameStatus.VARIANT_WIN
