"""Engine matching, FEN fallback, and hint square mapping."""

from pathlib import Path
from typing import Literal

from chess_core.app.engine import (
    EngineAnalysisService,
    EngineEvaluation,
    EngineHintService,
    EngineRequest,
    engine_family_for_mode,
    evaluation_from_white,
    fen_for_engine,
    select_engine_for_mode,
    suggested_squares_from_engine_move,
)
from chess_core.core.piece import PieceSide
from chess_core.infra.engines.discovery import EngineDescriptor
from chess_core.modes.chess import classic_chess, duck_chess, three_check_chess, two_move_chess
from chess_core.modes.checkers import checkers
from chess_core.modes.shogi import minishogi, shogi
from chess_core.modes.variant_composition import compose_chess_mode


def _engine(
    engine_id: str,
    variants: set[str],
    protocol: Literal["uci", "usi", "hub"] = "uci",
) -> EngineDescriptor:
    return EngineDescriptor(
        id=engine_id,
        name=engine_id,
        path=Path(f"{engine_id}.exe"),
        protocol=protocol,
        variants=frozenset(variants),
    )


def _catalog() -> list[EngineDescriptor]:
    return [
        _engine("stockfish", {"chess"}),
        _engine("yaneuraou", {"shogi"}, "usi"),
        _engine("scan", {"draughts", "checkers"}, "hub"),
    ]


def test_family_for_chess_variants() -> None:
    assert engine_family_for_mode(classic_chess(), registry_id="chess") == "chess"
    assert engine_family_for_mode(three_check_chess()) == "chess"
    assert engine_family_for_mode(two_move_chess()) == "chess"
    composed = compose_chess_mode(("fairytale", "three_check"))
    assert engine_family_for_mode(composed) == "chess"


def test_family_for_shogi_and_checkers() -> None:
    assert engine_family_for_mode(shogi()) == "shogi"
    assert engine_family_for_mode(minishogi()) == "shogi"
    assert engine_family_for_mode(checkers()) == "checkers"


def test_selects_stockfish_for_chess_family_without_exact_engine() -> None:
    chosen = select_engine_for_mode(three_check_chess(), _catalog(), registry_id="three_check")
    assert chosen is not None
    assert chosen.id == "stockfish"


def test_exact_variant_engine_beats_stockfish() -> None:
    engines = [
        *_catalog(),
        _engine("two-move-bot", {"two_move"}),
    ]
    chosen = select_engine_for_mode(two_move_chess(), engines, registry_id="two_move")
    assert chosen is not None
    assert chosen.id == "two-move-bot"


def test_classic_chess_matches_stockfish_by_registry_id() -> None:
    chosen = select_engine_for_mode(classic_chess(), _catalog(), registry_id="chess")
    assert chosen is not None
    assert chosen.id == "stockfish"


def test_shogi_and_minishogi_use_yaneuraou() -> None:
    assert select_engine_for_mode(shogi(), _catalog()).id == "yaneuraou"
    assert select_engine_for_mode(minishogi(), _catalog()).id == "yaneuraou"


def test_checkers_uses_scan() -> None:
    chosen = select_engine_for_mode(checkers(), _catalog())
    assert chosen is not None
    assert chosen.id == "scan"


def test_no_engine_for_unrelated_family() -> None:
    assert select_engine_for_mode(checkers(), [_engine("stockfish", {"chess"})]) is None


def test_hint_service_reports_missing_engine() -> None:
    service = EngineHintService(engines=())
    result = service.analyze(classic_chess(), classic_chess().initial_state())
    assert result.move_uci is None
    assert result.error == "Нет подходящего движка"


def test_hub_protocol_is_not_analyzed_yet() -> None:
    service = EngineAnalysisService(_engine("scan", {"checkers"}, "hub"))
    result = service.analyze(EngineRequest(checkers().initial_state()))
    assert result.error is not None
    assert "протокол" in result.error.lower()


def test_suggested_squares_from_uci_and_drop() -> None:
    assert suggested_squares_from_engine_move("e2e4", files=8, ranks=8) == (12, 28)
    assert suggested_squares_from_engine_move("a7a8q", files=8, ranks=8) == (48, 56)
    assert suggested_squares_from_engine_move("N@f3", files=8, ranks=8) == (21,)
    assert suggested_squares_from_engine_move("(none)", files=8, ranks=8) == ()
    assert suggested_squares_from_engine_move("not-a-move", files=8, ranks=8) == ()


def test_evaluation_is_converted_to_white_pov() -> None:
    raw = EngineEvaluation(score_cp=40, mate_in=None, pv=("e7e5",), depth=8)
    flipped = evaluation_from_white(raw, PieceSide.BLACK)
    assert flipped.score_cp == -40
    assert evaluation_from_white(raw, PieceSide.WHITE).score_cp == 40


def test_duck_fen_omits_the_blocker() -> None:
    mode = duck_chess()
    state = mode.initial_state()
    fen = fen_for_engine(state)
    assert fen.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")
