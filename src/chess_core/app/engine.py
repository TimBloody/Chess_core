"""Application-level engine analysis API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chess_core.core.gamemode import GameMode
from chess_core.core.notation import encode_board_placement, parse_square, parse_uci, to_fen
from chess_core.core.piece import Piece, PieceSide
from chess_core.core.sfen import to_sfen
from chess_core.core.state import GameState
from chess_core.infra.engines.discovery import EngineDescriptor, EngineDiscovery
from chess_core.infra.engines.uci import UciClient
from chess_core.infra.engines.usi import UsiClient

_CHESS_FEN_SYMBOLS = {
    "king": "k",
    "queen": "q",
    "rook": "r",
    "bishop": "b",
    "knight": "n",
    "pawn": "p",
}
_PREFERRED_ENGINE_IDS = {
    "chess": ("stockfish",),
    "shogi": ("yaneuraou", "fukaura"),
    "checkers": ("scan",),
}


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
    mode: GameMode | None = None


class EngineAnalysisService:
    def __init__(self, descriptor: EngineDescriptor) -> None:
        self._descriptor = descriptor

    def analyze(self, request: EngineRequest) -> BestMove:
        protocol = self._descriptor.protocol
        if protocol not in {"uci", "usi"}:
            return BestMove(
                None,
                None,
                error="протокол движка пока не поддерживает подсказки",
            )
        try:
            if protocol == "usi":
                usi_client = UsiClient(
                    str(self._descriptor.path),
                    movetime_ms=request.limit.movetime_ms,
                )
                usi_client.handshake()
                best, info = usi_client.analyze_sfen(to_sfen(request.state))
                usi_client.shutdown()
            else:
                uci_client = UciClient(
                    str(self._descriptor.path),
                    movetime_ms=request.limit.movetime_ms,
                )
                uci_client.handshake()
                best, info = uci_client.analyze_fen(fen_for_engine(request.state))
                uci_client.shutdown()
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            return BestMove(None, None, error=str(exc))
        evaluation = None
        if info is not None:
            evaluation = evaluation_from_white(
                EngineEvaluation(
                    score_cp=info.score_cp,
                    mate_in=info.mate_in,
                    pv=info.pv,
                    depth=info.depth,
                ),
                request.state.side_to_move,
            )
        return BestMove(move_uci=best, evaluation=evaluation)


class EngineHintService:
    """Pick the best available engine for a mode and analyse the current position."""

    def __init__(self, engines: Sequence[EngineDescriptor] | None = None) -> None:
        self._engines = list(engines) if engines is not None else None

    def engines(self) -> list[EngineDescriptor]:
        if self._engines is None:
            self._engines = discover_engines()
        return list(self._engines)

    def select(
        self, mode: GameMode, *, registry_id: str | None = None
    ) -> EngineDescriptor | None:
        return select_engine_for_mode(mode, self.engines(), registry_id=registry_id)

    def analyze(
        self,
        mode: GameMode,
        state: GameState,
        limit: SearchLimit | None = None,
        *,
        registry_id: str | None = None,
    ) -> BestMove:
        descriptor = self.select(mode, registry_id=registry_id)
        if descriptor is None:
            return BestMove(None, None, error="Нет подходящего движка")
        return EngineAnalysisService(descriptor).analyze(
            EngineRequest(state, limit or SearchLimit(), mode=mode)
        )


def discover_engines() -> list[EngineDescriptor]:
    discovery = EngineDiscovery()
    configured = discovery.load_config()
    if configured:
        return configured
    return discovery.scan()


def engine_family_for_mode(
    mode: GameMode, *, registry_id: str | None = None
) -> str | None:
    """Nearest engine family for a mode: chess, shogi, or checkers."""

    names = {piece.id.name for piece in mode.pieces.all_types()}
    root_ids = _root_ids(mode, registry_id)
    if any(name.startswith("checker") for name in names) or any(
        root.startswith("checkers") or root == "draughts" for root in root_ids
    ):
        return "checkers"
    if mode.asset_family in {"shogi", "dobutsu"} or "gold" in names or "lance" in names:
        return "shogi"
    if "pawn" in names and "king" in names and "rook" in names:
        return "chess"
    return None


def select_engine_for_mode(
    mode: GameMode,
    engines: Sequence[EngineDescriptor],
    *,
    registry_id: str | None = None,
) -> EngineDescriptor | None:
    """Exact mode id first, then the nearest family engine (Stockfish for chess)."""

    catalog = list(engines)
    if not catalog:
        return None
    family = engine_family_for_mode(mode, registry_id=registry_id)
    for key in _exact_mode_keys(mode, registry_id):
        matched = _engines_for_variant(catalog, key)
        if matched:
            return _prefer_engine(matched, family)
    if family is None:
        return None
    matched = _engines_for_variant(catalog, family)
    if not matched and family == "checkers":
        matched = _engines_for_variant(catalog, "draughts")
    if not matched:
        return None
    return _prefer_engine(matched, family)


def fen_for_engine(state: GameState) -> str:
    """FEN for a UCI engine; unknown/neutral pieces are omitted as empty squares."""

    try:
        return to_fen(state)
    except ValueError:
        return _tolerant_chess_fen(state)


def evaluation_from_white(
    evaluation: EngineEvaluation, side_to_move: PieceSide
) -> EngineEvaluation:
    """UCI scores are side-to-move; the eval bar is always white-positive."""

    if side_to_move is PieceSide.WHITE:
        return evaluation
    score = None if evaluation.score_cp is None else -evaluation.score_cp
    mate = None if evaluation.mate_in is None else -evaluation.mate_in
    return EngineEvaluation(
        score_cp=score,
        mate_in=mate,
        pv=evaluation.pv,
        depth=evaluation.depth,
    )


def suggested_squares_from_engine_move(
    move: str | None, *, files: int, ranks: int
) -> tuple[int, ...]:
    """Map a UCI/drop token such as ``e2e4`` or ``N@f3`` to board indices."""

    if move is None:
        return ()
    token = move.strip()
    if not token or token.lower() in {"(none)", "0000"}:
        return ()
    if "@" in token:
        dest = token.split("@", 1)[1]
        try:
            square = parse_square(dest, files, ranks)
        except ValueError:
            return ()
        return (square.index(files),)
    try:
        action = parse_uci(token.lower(), files=files, ranks=ranks)
    except ValueError:
        return ()
    return (action.from_square.index(files), action.to_square.index(files))


def _exact_mode_keys(mode: GameMode, registry_id: str | None) -> tuple[str, ...]:
    keys: list[str] = []
    for key in (mode.id, registry_id):
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _root_ids(mode: GameMode, registry_id: str | None) -> tuple[str, ...]:
    values: list[str] = []
    for raw in (mode.id, registry_id or ""):
        if raw:
            values.append(raw.split("+", 1)[0])
    return tuple(values)


def _engines_for_variant(
    engines: Sequence[EngineDescriptor], variant: str
) -> list[EngineDescriptor]:
    return [engine for engine in engines if variant in engine.variants]


def _prefer_engine(
    engines: Sequence[EngineDescriptor], family: str | None
) -> EngineDescriptor:
    preferred = _PREFERRED_ENGINE_IDS.get(family or "", ())
    for token in preferred:
        for engine in engines:
            blob = f"{engine.id} {engine.name}".lower()
            if token in blob:
                return engine
    return engines[0]


def _tolerant_chess_fen(state: GameState) -> str:
    def token(piece: Piece) -> str | None:
        if piece.side is PieceSide.NEUTRAL:
            return None
        symbol = _CHESS_FEN_SYMBOLS.get(piece.piece_type.name)
        if symbol is None:
            return None
        return symbol.upper() if piece.side is PieceSide.WHITE else symbol

    placement = encode_board_placement(state, token)
    active = "w" if state.side_to_move is PieceSide.WHITE else "b"
    rights = "".join(
        char for char in "KQkq" if char in state.extras.get("castling_rights", ())
    ) or "-"
    en_passant = state.extras.get("en_passant")
    ep_text = "-"
    if en_passant is not None:
        from chess_core.core.notation import square_name

        ep_text = square_name(en_passant)
    return (
        f"{placement} {active} {rights} {ep_text} "
        f"{state.extras.get('halfmove_clock', 0)} {state.extras.get('fullmove_number', 1)}"
    )
