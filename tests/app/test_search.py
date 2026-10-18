"""Built-in minimax and engine routing."""

from pathlib import Path

from chess_core.app.engine import EngineAnalysisService, EngineRequest, SearchLimit
from chess_core.app.engine_catalog import INTERNAL_MINIMAX, preferred_engine_ids, resolve_engine
from chess_core.app.search import MinimaxEngine
from chess_core.core.board import Square
from chess_core.core.move import MoveAction, PlaceBlockerAction, Turn
from chess_core.core.notation import parse_fen, to_engine_fen, to_sfen, with_partner_engine_fen
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.infra.engines.discovery import EngineDescriptor
from chess_core.modes.board_games import reversi
from chess_core.modes.bughouse import bughouse
from chess_core.modes.chess import (
    classic_chess,
    crazyhouse,
    duck_chess,
    giveaway,
    minichess,
)
from chess_core.modes.shogi import dobutsu_shogi, kyoto_shogi, shogi


def _reversi_cells(*occupied: tuple[int, PieceSide]) -> dict:
    from chess_core.core.piece import Piece, PieceTypeId

    disc = PieceTypeId("disc")
    cells = {index: None for index in range(64)}
    for index, side in occupied:
        cells[index] = Piece(disc, side)
    return cells


def test_reversi_search_prefers_a_corner_to_a_greedy_flip() -> None:
    from chess_core.modes.board_games import reversi

    mode = reversi()
    state = mode.initial_state()
    state.board_state.cells = _reversi_cells(
        (1, PieceSide.BLACK),
        (2, PieceSide.WHITE),
        (19, PieceSide.BLACK),
        (27, PieceSide.BLACK),
        (35, PieceSide.WHITE),
    )
    result = MinimaxEngine().search(state, depth=1, movetime_ms=800)
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert (drop.to_square.file, drop.to_square.rank) == (0, 0)


def test_reversi_search_avoids_an_x_square_next_to_an_empty_corner() -> None:
    from chess_core.modes.board_games import reversi

    mode = reversi()
    state = mode.initial_state()
    # a1 empty and not legal; b2 is the X-square; e3 is a quiet disc.
    state.board_state.cells = _reversi_cells(
        (18, PieceSide.BLACK),
        (27, PieceSide.WHITE),
        (28, PieceSide.BLACK),
        (36, PieceSide.WHITE),
    )
    result = MinimaxEngine().search(state, depth=1, movetime_ms=800)
    assert result.turn is not None
    drop = result.turn.actions[0]
    assert (drop.to_square.file, drop.to_square.rank) != (1, 1)


def test_minimax_finds_back_rank_mate_in_one() -> None:
    mode = classic_chess()
    state = parse_fen("6k1/8/6K1/8/8/8/8/R7 w - - 0 1", mode)
    result = MinimaxEngine().search(state, depth=1, movetime_ms=2000)
    assert result.turn is not None
    assert result.pv[0] == "a1a8"
    assert result.score_cp >= 90_000


def test_minimax_plays_a_legal_dobutsu_move() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    result = MinimaxEngine().search(state, depth=2, movetime_ms=1500)
    assert result.turn is not None
    assert result.turn.side is PieceSide.WHITE
    assert result.pv


def test_minimax_giveaway_picks_a_capture() -> None:
    mode = giveaway()
    state = parse_fen("4k3/8/8/8/8/8/r7/R3K3 w - - 0 1", mode)
    result = MinimaxEngine().search(state, depth=1, movetime_ms=1500)
    assert result.turn is not None
    assert result.pv[0] == "a1a2"


def test_minimax_minichess_returns_a_move() -> None:
    mode = minichess()
    result = MinimaxEngine().search(mode.initial_state(), depth=1, movetime_ms=1500)
    assert result.turn is not None
    assert len(result.pv[0]) >= 4


def test_analysis_service_uses_internal_engine_without_binaries() -> None:
    mode = minichess()
    service = EngineAnalysisService.for_mode(mode, discovered=[])
    best = service.analyze(EngineRequest(mode.initial_state(), SearchLimit(depth=1, movetime_ms=800)))
    assert best.engine_id == "minimax"
    assert best.move_uci
    assert best.error is None


def test_catalog_does_not_treat_fairy_as_stockfish() -> None:
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=Path("fairy-stockfish.exe"),
        protocol="uci",
        variants=frozenset({"chess", "crazyhouse", "giveaway"}),
    )
    choice = resolve_engine(classic_chess(), [fairy])
    assert choice.descriptor.id == "fairy-stockfish"
    crazy = resolve_engine(crazyhouse(), [fairy])
    assert crazy.uci_variant == "crazyhouse"

    assert preferred_engine_ids("chess")[0] == "stockfish"
    assert preferred_engine_ids("minichess") == ("fairy-stockfish", "minimax")
    assert preferred_engine_ids("reversi") == ("fairy-stockfish", "minimax")
    assert preferred_engine_ids("gobblet") == ("gobblet", "minimax")
    assert preferred_engine_ids("corners") == ("minimax",)
    assert preferred_engine_ids("draughts") == ("minimax",)
    fake = EngineDescriptor(
        id="stockfish",
        name="Stockfish",
        path=Path("stockfish.exe"),
        protocol="uci",
        variants=frozenset({"chess", "chess960"}),
    )
    choice = resolve_engine(classic_chess(), [fake])
    assert choice.descriptor.id == "stockfish"
    mini = resolve_engine(minichess(), [fake])
    assert mini.descriptor is INTERNAL_MINIMAX


def test_catalog_routes_supported_board_variants_to_fairy() -> None:
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=Path("fairy-stockfish.exe"),
        protocol="uci",
        variants=frozenset({"minichess", "reversi"}),
        options=(("VariantPath", "variants.ini"),),
    )
    mini = resolve_engine(minichess(), [fairy])
    assert mini.descriptor.id == "fairy-stockfish"
    assert mini.uci_variant == "gardner"
    othello = resolve_engine(reversi(), [fairy])
    assert othello.descriptor.id == "fairy-stockfish"
    assert othello.uci_variant == "flipello"


def test_duck_uses_allvars_fairy_only_with_compatible_rules() -> None:
    fairy = EngineDescriptor(
        id="fairy-stockfish-all",
        name="Fairy-Stockfish ALLVARS",
        path=Path("fairy-stockfish-all.exe"),
        protocol="uci",
        variants=frozenset({"duck"}),
    )
    assert resolve_engine(duck_chess(), [fairy]).descriptor is INTERNAL_MINIMAX
    choice = resolve_engine(duck_chess(fairy_rules=True), [fairy])
    assert choice.descriptor.id == "fairy-stockfish-all"
    assert choice.uci_variant == "duck"


def test_mixed_giveaway_fairy_uses_minimax() -> None:
    from chess_core.modes.orchestrator import compose_mode

    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=Path("fairy-stockfish.exe"),
        protocol="uci",
        variants=frozenset({"antichess", "giveaway"}),
    )
    choice = resolve_engine(compose_mode("chess+fairy+giveaway"), [fairy])
    assert choice.descriptor is INTERNAL_MINIMAX


def test_bughouse_routes_each_board_position_to_fairy() -> None:
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=Path("fairy-stockfish.exe"),
        protocol="uci",
        variants=frozenset({"bughouse"}),
    )
    choice = resolve_engine(bughouse(), [fairy])
    assert choice.descriptor.id == "fairy-stockfish"
    assert choice.uci_variant == "bughouse"


def test_shogi_sfen_startpos() -> None:
    fen = to_sfen(shogi().initial_state())
    assert fen == "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"


def test_catalog_prefers_fairy_for_dobutsu_and_kyoto() -> None:
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=Path("fairy-stockfish.exe"),
        protocol="uci",
        variants=frozenset({"dobutsu_shogi", "kyoto_shogi", "crazyhouse"}),
    )
    dobutsu = resolve_engine(dobutsu_shogi(), [fairy])
    assert dobutsu.descriptor.id == "fairy-stockfish"
    assert dobutsu.uci_variant == "dobutsu"
    kyoto = resolve_engine(kyoto_shogi(), [fairy])
    assert kyoto.descriptor.id == "fairy-stockfish"
    assert kyoto.uci_variant == "kyotoshogi"
    assert preferred_engine_ids("dobutsu_shogi")[0] == "fairy-stockfish"
    without = resolve_engine(dobutsu_shogi(), [])
    assert without.descriptor is INTERNAL_MINIMAX


def test_dobutsu_and_kyoto_engine_fen() -> None:
    assert to_engine_fen(shogi().initial_state()) == "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL[-] w 0 1"
    assert to_engine_fen(dobutsu_shogi().initial_state()) == "elg/1c1/1C1/GLE[-] w 0 1"
    assert to_engine_fen(kyoto_shogi().initial_state()) == "p+nks+l/5/5/5/+LSK+NP[-] w 0 1"
    assert to_engine_fen(reversi().initial_state()) == "8/8/8/3Pp3/3pP3/8/8/8[PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPpppppppppppppppppppppppppppppppp] w 0 1"


def test_bughouse_engine_fen_includes_partner_board_and_gifts() -> None:
    mode = bughouse()
    own = mode.initial_state()
    partner = mode.initial_state()
    assert partner.hands is not None
    partner.hands.add(PieceSide.BLACK, Piece(PieceTypeId("pawn"), PieceSide.BLACK))
    fen = to_engine_fen(with_partner_engine_fen(own, partner))
    own_fen, partner_fen = fen.split(" | ")
    assert own_fen.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR[]")
    assert "[p]" in partner_fen


def test_duck_engine_fen_includes_neutral_blocker() -> None:
    mode = duck_chess(fairy_rules=True)
    state = mode.initial_state().apply_turn(
        Turn(
            PieceSide.WHITE,
            [
                MoveAction(Square(0, 1), Square(0, 2)),
                PlaceBlockerAction(Square(0, 1)),
            ],
        )
    )
    assert to_engine_fen(state).startswith(
        "rnbqkbnr/pppppppp/8/8/8/P7/*PPPPPPP/RNBQKBNR b"
    )


def test_allvars_fairy_plays_legal_duck_turn() -> None:
    root = Path(__file__).resolve().parents[1].parent
    exe = root / "engines" / "public" / "fairystockfish-all" / "fairy-stockfish-all.exe"
    if not exe.is_file():
        return
    fairy = EngineDescriptor(
        id="fairy-stockfish-all",
        name="Fairy-Stockfish ALLVARS",
        path=exe,
        protocol="uci",
        variants=frozenset({"duck"}),
    )
    mode = duck_chess(fairy_rules=True)
    service = EngineAnalysisService.for_mode(mode, discovered=[fairy])
    try:
        best = service.analyze(
            EngineRequest(mode.initial_state(), SearchLimit(movetime_ms=200))
        )
        assert best.engine_id == "fairy-stockfish-all"
        assert best.turn is not None
        assert len(best.turn.actions) == 2
    finally:
        service.close()


def test_fairy_plays_legal_shogi_minichess_and_reversi_turns() -> None:
    root = Path(__file__).resolve().parents[1].parent
    exe = root / "engines" / "public" / "fairystockfish" / "fairy-stockfish.exe"
    variants_ini = exe.parent / "variants.ini"
    if not exe.is_file() or not variants_ini.is_file():
        return
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=exe,
        protocol="uci",
        variants=frozenset({"shogi", "minichess", "reversi", "bughouse"}),
        options=(("VariantPath", str(variants_ini)),),
    )
    for mode in (shogi(), minichess(), reversi(), bughouse()):
        service = EngineAnalysisService.for_mode(mode, discovered=[fairy])
        try:
            best = service.analyze(
                EngineRequest(mode.initial_state(), SearchLimit(movetime_ms=200))
            )
            assert best.engine_id == "fairy-stockfish"
            assert best.turn is not None
            after = mode.initial_state().apply_turn(best.turn, record_history=False)
            assert after.side_to_move is PieceSide.BLACK
        finally:
            service.close()


def test_fairy_plays_legal_kyoto_turn() -> None:
    exe = Path(__file__).resolve().parents[1].parent / "engines" / "public" / "fairystockfish" / "fairy-stockfish.exe"
    if not exe.is_file():
        return
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=exe,
        protocol="uci",
        variants=frozenset({"kyoto_shogi"}),
    )
    mode = kyoto_shogi()
    service = EngineAnalysisService.for_mode(mode, discovered=[fairy])
    try:
        best = service.analyze(EngineRequest(mode.initial_state(), SearchLimit(movetime_ms=400)))
        assert best.engine_id == "fairy-stockfish"
        assert best.turn is not None
        after = mode.initial_state().apply_turn(best.turn, record_history=False)
        assert after.side_to_move is PieceSide.BLACK
    finally:
        service.close()


def test_fairy_plays_legal_dobutsu_turn() -> None:
    exe = Path(__file__).resolve().parents[1].parent / "engines" / "public" / "fairystockfish" / "fairy-stockfish.exe"
    if not exe.is_file():
        return
    fairy = EngineDescriptor(
        id="fairy-stockfish",
        name="Fairy-Stockfish",
        path=exe,
        protocol="uci",
        variants=frozenset({"dobutsu_shogi"}),
    )
    mode = dobutsu_shogi()
    service = EngineAnalysisService.for_mode(mode, discovered=[fairy])
    try:
        best = service.analyze(EngineRequest(mode.initial_state(), SearchLimit(movetime_ms=400)))
        assert best.engine_id == "fairy-stockfish"
        assert best.turn is not None
        after = mode.initial_state().apply_turn(best.turn, record_history=False)
        assert after.side_to_move is PieceSide.BLACK
    finally:
        service.close()
