"""Application-level engine analysis API."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.notation import to_fen
from chess_core.core.state import GameState
from chess_core.infra.engines.discovery import EngineDescriptor, EngineDiscovery
from chess_core.infra.engines.uci import UciClient
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


@dataclass(frozen=True, slots=True)
class EngineRequest:
    state: GameState
    limit: SearchLimit = SearchLimit()


class EngineAnalysisService:
    def __init__(self, descriptor: EngineDescriptor) -> None:
        self._descriptor = descriptor

    def analyze(self, request: EngineRequest) -> BestMove:
        if "chess" not in self._descriptor.variants and self._descriptor.protocol == "uci":
            return BestMove(None, None, error="engine does not support this variant")
        try:
            if self._descriptor.protocol == "usi":
                client: UciClient = UsiClient(
                    str(self._descriptor.path),
                    movetime_ms=request.limit.movetime_ms,
                )
                client.handshake()
                fen = to_fen(request.state)
                best, info = client.analyze_sfen(fen)
            else:
                client = UciClient(
                    str(self._descriptor.path),
                    movetime_ms=request.limit.movetime_ms,
                )
                client.handshake()
                fen = to_fen(request.state)
                best, info = client.analyze_fen(fen)
            client.shutdown()
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            return BestMove(None, None, error=str(exc))
        evaluation = None
        if info is not None:
            evaluation = EngineEvaluation(
                score_cp=info.score_cp,
                mate_in=info.mate_in,
                pv=info.pv,
                depth=info.depth,
            )
        return BestMove(move_uci=best, evaluation=evaluation)


def discover_engines() -> list[EngineDescriptor]:
    discovery = EngineDiscovery()
    configured = discovery.load_config()
    if configured:
        return configured
    return discovery.scan()
