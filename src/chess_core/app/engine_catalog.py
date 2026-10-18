"""Preferred engine backend for each game mode."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from chess_core.core.gamemode import GameMode
from chess_core.infra.engines.discovery import EngineDescriptor

INTERNAL_MINIMAX = EngineDescriptor(
    id="minimax",
    name="Built-in minimax",
    path=Path(),
    protocol="internal",
    variants=frozenset({"*"}),
)

INTERNAL_GOBBLET = EngineDescriptor(
    id="gobblet",
    name="Gobblet AlphaZero + exact probes",
    path=Path(),
    protocol="internal",
    variants=frozenset({"gobblet"}),
)

# Registry ids and GameMode.id values both appear here.
# External engines are used only when a binary is present AND the position
# can be serialized (FEN/SFEN). Otherwise the built-in alpha-beta runs.
_PREFERRED: dict[str, tuple[str, ...]] = {
    "chess": ("stockfish", "fairy-stockfish", "minimax"),
    "classic_chess": ("stockfish", "fairy-stockfish", "minimax"),
    "chess960": ("stockfish", "fairy-stockfish", "minimax"),
    "hand_and_brain": ("stockfish", "fairy-stockfish", "minimax"),
    "crazyhouse": ("fairy-stockfish", "minimax"),
    "giveaway": ("fairy-stockfish", "minimax"),
    "duck": ("fairy-stockfish-all", "minimax"),
    "duck_chess": ("fairy-stockfish-all", "minimax"),
    "shogi": ("yaneuraou", "fairy-stockfish", "minimax"),
    "kyoto_shogi": ("fairy-stockfish", "minimax"),
    "dobutsu_shogi": ("fairy-stockfish", "minimax"),
    "minichess": ("fairy-stockfish", "minimax"),
    "cylindrical": ("minimax",),
    "cylindrical_chess": ("minimax",),
    "bughouse": ("fairy-stockfish", "minimax"),
    "reversi": ("fairy-stockfish", "minimax"),
    "corners": ("minimax",),
    "draughts": ("minimax",),
    "nanai_checkers": ("minimax",),
    "hasami_shogi": ("minimax",),
    "gobblet": ("gobblet", "minimax"),
}

_UCI_VARIANT: dict[str, str] = {
    "crazyhouse": "crazyhouse",
    "giveaway": "antichess",
    "shogi": "shogi",
    "kyoto_shogi": "kyotoshogi",
    "dobutsu_shogi": "dobutsu",
    "minichess": "gardner",
    "reversi": "flipello",
    "bughouse": "bughouse",
    "duck": "duck",
    "duck_chess": "duck",
}

_ALIASES = {
    "classic_chess": "chess",
    "duck_chess": "duck",
    "cylindrical_chess": "cylindrical",
}


@dataclass(frozen=True, slots=True)
class EngineChoice:
    descriptor: EngineDescriptor
    uci_variant: str | None = None
    chess960: bool = False
    use_sfen: bool = False


def preferred_engine_ids(mode_id: str) -> tuple[str, ...]:
    return _PREFERRED.get(mode_id, _PREFERRED.get(_ALIASES.get(mode_id, ""), ("minimax",)))


def uci_variant_for(mode_id: str) -> str | None:
    return _UCI_VARIANT.get(mode_id) or _UCI_VARIANT.get(_ALIASES.get(mode_id, ""), None)


def resolve_engine(mode: GameMode, discovered: list[EngineDescriptor]) -> EngineChoice:
    """Pick the strongest available backend for ``mode``, else built-in minimax."""
    layers = _mode_layers(mode)
    chess960 = mode.id == "chess960" or "chess960_position" in mode.initial_extras
    variant = _uci_variant_for_mode(mode, layers)
    preferred = _preferred_for_mode(mode.id, layers)
    if "duck" in layers and not mode.initial_extras.get("fairy_duck_rules"):
        preferred = ("minimax",)
    if "cylindrical" in layers:
        preferred = ("minimax",)
    # Fairytale file-movement is not expressible as a UCI variant.
    if "fairy" in layers and "duck" not in layers:
        preferred = ("minimax",)
    if len(layers) > 1 and variant is None:
        preferred = ("minimax",)
    for engine_id in preferred:
        if engine_id == "minimax":
            return EngineChoice(INTERNAL_MINIMAX)
        if engine_id == "gobblet":
            return EngineChoice(INTERNAL_GOBBLET)
        match = _find(discovered, engine_id)
        if match is None:
            continue
        probe_id = mode.id if "+" not in mode.id else next(iter(layers), mode.id)
        if not _supports_mode(match, probe_id) and not _supports_mode(match, mode.id):
            if variant is None:
                continue
        options: list[tuple[str, str]] = list(match.options)
        if variant and match.protocol == "uci":
            options.append(("UCI_Variant", variant))
        if chess960 and match.protocol == "uci":
            options.append(("UCI_Chess960", "true"))
        descriptor = replace(match, options=tuple(options)) if options else match
        return EngineChoice(
            descriptor=descriptor,
            uci_variant=variant,
            chess960=chess960,
            use_sfen=match.protocol == "usi",
        )
    return EngineChoice(INTERNAL_MINIMAX)


def _mode_layers(mode: GameMode) -> frozenset[str]:
    raw = mode.initial_extras.get("mode_layers")
    if isinstance(raw, (tuple, list, set, frozenset)):
        return frozenset(str(item) for item in raw)
    from chess_core.modes.orchestrator import parse_spec

    try:
        return parse_spec(mode.id).layers
    except ValueError:
        return frozenset()


def _preferred_for_mode(mode_id: str, layers: frozenset[str]) -> tuple[str, ...]:
    if mode_id in _PREFERRED:
        return preferred_engine_ids(mode_id)
    if "gobblet" in mode_id:
        return ("gobblet", "minimax")
    if layers <= {"giveaway"}:
        return preferred_engine_ids("giveaway")
    if layers <= {"crazyhouse"}:
        return preferred_engine_ids("crazyhouse")
    if layers <= {"chess960"}:
        return preferred_engine_ids("chess960")
    if layers <= {"bughouse"}:
        return preferred_engine_ids("bughouse")
    if layers <= {"duck", "fairy"}:
        return preferred_engine_ids("duck")
    if layers <= {"hand_and_brain"}:
        return preferred_engine_ids("hand_and_brain")
    return ("minimax",)


def _uci_variant_for_mode(mode: GameMode, layers: frozenset[str]) -> str | None:
    direct = uci_variant_for(mode.id)
    if direct:
        return direct
    if layers == {"giveaway"}:
        return "antichess"
    if layers == {"crazyhouse"}:
        return "crazyhouse"
    if layers == {"bughouse"}:
        return "bughouse"
    if layers == {"duck", "fairy"} or layers == {"duck"}:
        return "duck" if mode.initial_extras.get("fairy_duck_rules") else None
    return None


def _find(discovered: list[EngineDescriptor], engine_id: str) -> EngineDescriptor | None:
    needle = engine_id.lower().replace("-", "")
    ranked: list[EngineDescriptor] = []
    for descriptor in discovered:
        ident = descriptor.id.lower().replace("-", "")
        stem = descriptor.path.stem.lower().replace("-", "")
        if ident == needle or stem == needle or ident.startswith(needle) or stem.startswith(needle):
            ranked.append(descriptor)
    if not ranked:
        return None
    ranked.sort(key=lambda item: ("material" in item.id.lower(), item.id.lower()))
    return ranked[0]


def _supports_mode(descriptor: EngineDescriptor, mode_id: str) -> bool:
    if "*" in descriptor.variants:
        return True
    aliases = {mode_id, _ALIASES.get(mode_id, mode_id)}
    if descriptor.variants & aliases:
        return True
    if mode_id in {"chess", "classic_chess", "chess960", "hand_and_brain"}:
        return "chess" in descriptor.variants
    return False
