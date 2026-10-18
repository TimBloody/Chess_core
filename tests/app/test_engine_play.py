"""Map engine bestmoves onto legal turns."""

from chess_core.app.engine import BestMove, EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.app.engine_play import resolve_engine_turn
from chess_core.core.board import Square
from chess_core.core.move import DropAction, PlaceBlockerAction
from chess_core.core.movegen import MoveGenerator
from chess_core.core.notation import format_usi_action
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import classic_chess, crazyhouse, duck_chess
from chess_core.modes.shogi import kyoto_shogi, shogi

import pytest


def test_resolve_uci_e2e4() -> None:
    mode = classic_chess()
    state = mode.initial_state()
    turn = resolve_engine_turn(state, BestMove("e2e4", None))
    assert turn is not None
    assert turn.side is PieceSide.WHITE
    move = turn.actions[0]
    assert (move.from_square.file, move.from_square.rank) == (4, 1)
    assert (move.to_square.file, move.to_square.rank) == (4, 3)


def test_resolve_usi_sente_pawn() -> None:
    mode = shogi()
    state = mode.initial_state()
    pawn = next(
        action
        for action in MoveGenerator(mode).generate_legal(state)
        if getattr(action, "from_square", None) is not None
        and action.from_square.file == 2
        and action.from_square.rank == 2
    )
    token = format_usi_action(pawn, files=9, ranks=9)
    turn = resolve_engine_turn(state, BestMove(token, None))
    assert turn is not None
    assert turn.actions[0].from_square == pawn.from_square
    assert turn.actions[0].to_square == pawn.to_square


def test_minimax_bestmove_includes_playable_turn() -> None:
    mode = classic_chess()
    service = EngineAnalysisService.for_mode(mode, discovered=[])
    best = service.analyze(EngineRequest(mode.initial_state(), SearchLimit(depth=1, movetime_ms=800)))
    assert best.turn is not None
    after = mode.initial_state().apply_turn(best.turn, record_history=False)
    assert after.side_to_move is PieceSide.BLACK


def test_resolve_kyoto_fairy_demotion_suffix() -> None:
    mode = kyoto_shogi()
    state = mode.initial_state()
    turn = resolve_engine_turn(state, BestMove("a1b2-", None))
    assert turn is not None
    move = turn.actions[0]
    assert (move.from_square.file, move.from_square.rank) == (0, 0)
    assert (move.to_square.file, move.to_square.rank) == (1, 1)


def test_resolve_kyoto_fairy_promoted_drop() -> None:
    mode = kyoto_shogi()
    state = mode.initial_state()
    assert state.hands is not None
    state.hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    turn = resolve_engine_turn(state, BestMove("+P@c3", None))
    assert turn is not None
    action = turn.actions[0]
    assert isinstance(action, DropAction)
    assert action.face == "rook"
    assert action.to_square == Square(2, 2)


def test_crazyhouse_drop_token() -> None:
    mode = crazyhouse()
    state = mode.initial_state()
    assert state.hands is not None
    state.hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    turn = resolve_engine_turn(state, BestMove("P@e4", None))
    assert turn is not None
    action = turn.actions[0]
    assert isinstance(action, DropAction)
    assert action.to_square == Square(4, 3)
    assert action.piece_type.name == "pawn"


def test_resolve_fairy_duck_compound_move() -> None:
    mode = duck_chess(fairy_rules=True)
    turn = resolve_engine_turn(
        mode.initial_state(),
        BestMove("a2a3,a3a2", None),
    )
    assert turn is not None
    assert turn.actions[0].from_square == Square(0, 1)
    assert turn.actions[0].to_square == Square(0, 2)
    assert isinstance(turn.actions[1], PlaceBlockerAction)
    assert turn.actions[1].square == Square(0, 1)


@pytest.mark.parametrize(
    "mode_id",
    (
        "chess",
        "chess960",
        "crazyhouse",
        "giveaway",
        "minichess",
        "cylindrical",
        "duck",
        "shogi",
        "kyoto_shogi",
        "dobutsu_shogi",
        "reversi",
        "corners",
        "draughts",
        "gobblet",
        "nanai_checkers",
        "hasami_shogi",
    ),
)
def test_minimax_can_play_a_turn_in_each_local_mode(mode_id: str) -> None:
    register_builtin_modes()
    mode = default_registry.get(mode_id)
    service = EngineAnalysisService.for_mode(mode, discovered=[])
    start = mode.initial_state()
    best = service.analyze(EngineRequest(start, SearchLimit(depth=1, movetime_ms=1500)))
    assert best.error is None
    assert best.turn is not None
    after = start.apply_turn(best.turn, record_history=False)
    assert after.side_to_move is not start.side_to_move
