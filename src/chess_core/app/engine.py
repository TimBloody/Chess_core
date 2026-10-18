"""Application-level engine analysis API."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.app.engine_catalog import EngineChoice, INTERNAL_MINIMAX, resolve_engine
from chess_core.app.search import MinimaxEngine
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Turn
from chess_core.core.notation import to_engine_fen, to_sfen
from chess_core.core.piece import PieceSide
from chess_core.core.state import GameState
from chess_core.infra.engines.discovery import EngineDescriptor, EngineDiscovery
from chess_core.infra.engines.uci import UciClient, UciInfo
from chess_core.infra.engines.usi import UsiClient


@dataclass(frozen=True, slots=True)
class SearchLimit:
    movetime_ms: int = 500
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class EngineEvaluation:
    score_cp: int | None
    mate_in: int | None
    pv: tuple[str, ...]
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class BestMove:
    move_uci: str | None
    evaluation: EngineEvaluation | None
    error: str | None = None
    engine_id: str | None = None
    turn: Turn | None = None
    purpose: str = "analyze"
    revision: int = 0


@dataclass(frozen=True, slots=True)
class EngineRequest:
    state: GameState
    limit: SearchLimit = SearchLimit()
    purpose: str = "analyze"
    revision: int = 0


class EngineAnalysisService:
    def __init__(self, descriptor: EngineDescriptor, *, choice: EngineChoice | None = None) -> None:
        self._descriptor = descriptor
        self._choice = choice or EngineChoice(descriptor)
        self._client: UciClient | None = None

    @property
    def descriptor(self) -> EngineDescriptor:
        return self._descriptor

    def close(self) -> None:
        if self._client is not None:
            self._client.shutdown()
            self._client = None

    def stop_search(self) -> None:
        if self._client is not None:
            self._client.stop_search()

    @classmethod
    def for_mode(cls, mode: GameMode, discovered: list[EngineDescriptor] | None = None) -> EngineAnalysisService:
        choice = resolve_engine(mode, discovered if discovered is not None else discover_engines())
        return cls(choice.descriptor, choice=choice)

    def analyze(self, request: EngineRequest) -> BestMove:
        state = request.state.clone(include_history=False)
        if self._descriptor.protocol == "internal":
            return self._with_meta(self._analyze_internal(state, request.limit), request)
        try:
            return self._with_meta(self._analyze_external(state, request.limit), request)
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            fallback = self._analyze_internal(state, request.limit)
            if fallback.error:
                return BestMove(
                    None,
                    None,
                    error=str(exc),
                    engine_id=self._descriptor.id,
                    purpose=request.purpose,
                    revision=request.revision,
                )
            return BestMove(
                move_uci=fallback.move_uci,
                evaluation=fallback.evaluation,
                error=None,
                engine_id=f"{self._descriptor.id}+minimax",
                turn=fallback.turn,
                purpose=request.purpose,
                revision=request.revision,
            )

    def _analyze_internal(self, state: GameState, limit: SearchLimit) -> BestMove:
        if self._descriptor.id == "gobblet":
            from chess_core.app.gobblet_engine import GobbletEngine

            result = GobbletEngine().search(
                state,
                depth=limit.depth,
                movetime_ms=limit.movetime_ms,
            )
            engine_id = "gobblet"
        else:
            result = MinimaxEngine().search(
                state,
                depth=limit.depth,
                movetime_ms=limit.movetime_ms,
            )
            engine_id = "minimax"
        score = result.score_cp
        if state.side_to_move is PieceSide.BLACK:
            score = -score
            mate = -result.mate_in if result.mate_in is not None else None
        else:
            mate = result.mate_in
        evaluation = EngineEvaluation(
            score_cp=score,
            mate_in=mate,
            pv=result.pv,
            depth=result.depth,
        )
        move_uci = result.pv[0] if result.pv else None
        return BestMove(
            move_uci=move_uci,
            evaluation=evaluation,
            engine_id=engine_id,
            turn=result.turn,
        )

    def _analyze_external(self, state: GameState, limit: SearchLimit) -> BestMove:
        client = self._external_client()
        if self._descriptor.protocol == "usi":
            best, info = client.analyze_sfen(
                to_sfen(state),
                movetime_ms=limit.movetime_ms,
                depth=limit.depth,
            )
        else:
            fen = to_sfen(state) if self._choice.use_sfen else to_engine_fen(state)
            best, info = client.analyze_fen(
                fen,
                movetime_ms=limit.movetime_ms,
                depth=limit.depth,
            )
        result = BestMove(
            move_uci=best,
            evaluation=_info_to_eval(info, state.side_to_move),
            engine_id=self._descriptor.id,
        )
        from chess_core.app.engine_play import resolve_engine_turn

        turn = resolve_engine_turn(state, result)
        if turn is None:
            fallback = self._analyze_internal(state, limit)
            return BestMove(
                move_uci=fallback.move_uci or result.move_uci,
                evaluation=result.evaluation or fallback.evaluation,
                engine_id=f"{self._descriptor.id}+minimax",
                turn=fallback.turn,
            )
        return BestMove(
            move_uci=result.move_uci,
            evaluation=result.evaluation,
            engine_id=result.engine_id,
            turn=turn,
        )

    def _external_client(self) -> UciClient:
        if self._client is not None:
            return self._client
        options = dict(self._descriptor.options)
        path = str(self._descriptor.path)
        if self._descriptor.protocol == "usi":
            self._client = UsiClient(path, options=options)
        else:
            self._client = UciClient(path, options=options)
        self._client.handshake()
        return self._client

    @staticmethod
    def _with_meta(result: BestMove, request: EngineRequest) -> BestMove:
        return BestMove(
            move_uci=result.move_uci,
            evaluation=result.evaluation,
            error=result.error,
            engine_id=result.engine_id,
            turn=result.turn,
            purpose=request.purpose,
            revision=request.revision,
        )


def _info_to_eval(info: UciInfo | None, side: PieceSide) -> EngineEvaluation | None:
    if info is None:
        return None
    score = info.score_cp
    mate = info.mate_in
    if side is PieceSide.BLACK:
        if score is not None:
            score = -score
        if mate is not None:
            mate = -mate
    return EngineEvaluation(score_cp=score, mate_in=mate, pv=info.pv, depth=info.depth)


def discover_engines() -> list[EngineDescriptor]:
    discovery = EngineDiscovery()
    configured = discovery.load_config()
    scanned = discovery.scan()
    by_id = {item.id: item for item in scanned}
    for item in configured:
        by_id[item.id] = item
    return list(by_id.values()) or [INTERNAL_MINIMAX]
