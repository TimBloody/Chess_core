"""Compose a GameMode from a base family plus compatible overlay layers.

Standalone registry ids such as ``giveaway`` stay as aliases. Combinations
are ``chess+cylindrical+giveaway``. UI checkboxes talk to this module, not
to ``if mode.id == ...`` branches in movegen.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

from chess_core.core.gamemode import GameMode
from chess_core.core.rules import CaptureSink, VictoryCondition, VictoryKind
from chess_core.core.turn import StepKind, TurnScenario, TurnStep

BASE_ORDER: tuple[str, ...] = (
    "chess",
    "minichess",
    "shogi",
    "kyoto_shogi",
    "dobutsu_shogi",
    "hasami_shogi",
    "reversi",
    "corners",
    "draughts",
    "nanai_checkers",
    "gobblet",
)

FAMILY_ORDER: tuple[str, ...] = ("chess", "shogi", "board")

FAMILY_LABELS: dict[str, str] = {
    "chess": "Шахматы",
    "shogi": "Сёги",
    "board": "Шашки",
}

FAMILY_BASES: dict[str, tuple[str, ...]] = {
    "chess": ("chess", "minichess"),
    "shogi": ("shogi", "kyoto_shogi", "dobutsu_shogi", "hasami_shogi"),
    "board": ("draughts", "corners", "reversi", "gobblet", "nanai_checkers"),
}

_BASE_FACTORIES: dict[str, tuple[str, str]] = {
    "chess": ("chess_core.modes.chess", "classic_chess"),
    "minichess": ("chess_core.modes.chess", "minichess"),
    "shogi": ("chess_core.modes.shogi", "shogi"),
    "kyoto_shogi": ("chess_core.modes.shogi", "kyoto_shogi"),
    "dobutsu_shogi": ("chess_core.modes.shogi", "dobutsu_shogi"),
    "hasami_shogi": ("chess_core.modes.hasami_shogi", "hasami_shogi"),
    "reversi": ("chess_core.modes.board_games", "reversi"),
    "corners": ("chess_core.modes.board_games", "corners"),
    "draughts": ("chess_core.modes.board_games", "draughts"),
    "nanai_checkers": ("chess_core.modes.nanai_checkers", "nanai_checkers"),
    "gobblet": ("chess_core.modes.gobblet", "gobblet"),
}

_PRESET_ALIASES: dict[str, tuple[str, frozenset[str]]] = {
    "chess": ("chess", frozenset()),
    "classic_chess": ("chess", frozenset()),
    "minichess": ("minichess", frozenset()),
    "shogi": ("shogi", frozenset()),
    "kyoto_shogi": ("kyoto_shogi", frozenset()),
    "dobutsu_shogi": ("dobutsu_shogi", frozenset()),
    "hasami_shogi": ("hasami_shogi", frozenset()),
    "reversi": ("reversi", frozenset()),
    "corners": ("corners", frozenset()),
    "draughts": ("draughts", frozenset()),
    "nanai_checkers": ("nanai_checkers", frozenset()),
    "gobblet": ("gobblet", frozenset()),
    "giveaway": ("chess", frozenset({"giveaway"})),
    "crazyhouse": ("chess", frozenset({"crazyhouse"})),
    "chess960": ("chess", frozenset({"chess960"})),
    "cylindrical": ("chess", frozenset({"cylindrical"})),
    "cylindrical_chess": ("chess", frozenset({"cylindrical"})),
    "duck": ("chess", frozenset({"duck"})),
    "duck_chess": ("chess", frozenset({"duck"})),
    "fairy": ("chess", frozenset({"fairy"})),
    "fairytale": ("chess", frozenset({"fairy"})),
    "bughouse": ("chess", frozenset({"bughouse"})),
    "hand_and_brain": ("chess", frozenset({"hand_and_brain"})),
}

_ENCODE_ALIASES: dict[tuple[str, frozenset[str]], str] = {
    (base, layers): alias for alias, (base, layers) in _PRESET_ALIASES.items()
    if alias not in {"classic_chess", "cylindrical_chess", "duck_chess", "fairytale"}
}


@dataclass(frozen=True, slots=True)
class ModeSpec:
    """One playable combination: a base family plus overlay layer ids."""

    base: str
    layers: frozenset[str] = field(default_factory=frozenset)

    def encoded(self) -> str:
        key = (self.base, self.layers)
        if key in _ENCODE_ALIASES:
            return _ENCODE_ALIASES[key]
        if not self.layers:
            return self.base
        return self.base + "+" + "+".join(sorted(self.layers))


@dataclass(frozen=True, slots=True)
class ModeLayer:
    id: str
    label: str
    applies_to: frozenset[str]
    conflicts: frozenset[str] = field(default_factory=frozenset)
    apply: Callable[[GameMode], GameMode] = field(repr=False, compare=False, default=lambda mode: mode)


def parse_spec(mode_id: str) -> ModeSpec:
    token = mode_id.strip()
    if not token:
        raise ValueError("mode id must not be empty")
    if token in _PRESET_ALIASES:
        base, layers = _PRESET_ALIASES[token]
        return ModeSpec(base, layers)
    if "+" not in token:
        if token in _BASE_FACTORIES:
            return ModeSpec(token, frozenset())
        raise ValueError(f"unknown game mode: {token}")
    parts = [part for part in token.split("+") if part]
    if not parts:
        raise ValueError(f"unknown game mode: {token}")
    head, *rest = parts
    if head in _PRESET_ALIASES:
        base, preset_layers = _PRESET_ALIASES[head]
        extra = {
            _coerce_layer(part)
            for part in rest
            if part not in {base, head}
        }
        return ModeSpec(base, frozenset(preset_layers | extra))
    if head not in _BASE_FACTORIES:
        raise ValueError(f"unknown game mode: {token}")
    return ModeSpec(head, frozenset(_coerce_layer(part) for part in rest))


def _coerce_layer(token: str) -> str:
    if token in LAYERS:
        return token
    mapped = _PRESET_ALIASES.get(token)
    if mapped is not None:
        _base, layers = mapped
        if len(layers) == 1:
            return next(iter(layers))
    raise ValueError(f"unknown mode layer: {token}")


def compose_mode(mode_id: str) -> GameMode:
    """Build a GameMode for a preset or ``base+layer+layer`` id."""
    return orchestrate(parse_spec(mode_id))


def orchestrate(spec: ModeSpec) -> GameMode:
    _validate(spec)
    mode = _base_mode(spec.base)
    for layer_id in _APPLY_ORDER:
        if layer_id in spec.layers:
            mode = LAYERS[layer_id].apply(mode)
    extras = dict(mode.initial_extras)
    extras["mode_layers"] = tuple(sorted(spec.layers))
    extras["mode_base"] = spec.base
    encoded = spec.encoded()
    return replace(
        mode,
        id=encoded,
        name=spec_display_name(spec),
        initial_extras=extras,
    )


def compatible_layers(base: str, selected: frozenset[str]) -> frozenset[str]:
    allowed: set[str] = set()
    for layer_id, layer in LAYERS.items():
        if base not in layer.applies_to:
            continue
        others = selected - {layer_id}
        if layer.conflicts & others:
            continue
        allowed.add(layer_id)
    return frozenset(allowed)


def toggle_layer(spec: ModeSpec, layer_id: str, enabled: bool) -> ModeSpec:
    if layer_id not in LAYERS:
        raise ValueError(f"unknown mode layer: {layer_id}")
    layer = LAYERS[layer_id]
    selected = set(spec.layers)
    if not enabled:
        selected.discard(layer_id)
        return ModeSpec(spec.base, frozenset(selected))
    if spec.base not in layer.applies_to:
        raise ValueError(f"layer {layer_id} does not apply to {spec.base}")
    selected -= set(layer.conflicts)
    selected.add(layer_id)
    return ModeSpec(spec.base, frozenset(selected))


def _validate(spec: ModeSpec) -> None:
    if spec.base not in _BASE_FACTORIES:
        raise ValueError(f"unknown game mode: {spec.base}")
    for layer_id in spec.layers:
        if layer_id not in LAYERS:
            raise ValueError(f"unknown mode layer: {layer_id}")
        layer = LAYERS[layer_id]
        if spec.base not in layer.applies_to:
            raise ValueError(f"layer {layer_id} does not apply to {spec.base}")
        clash = layer.conflicts & spec.layers
        if clash:
            raise ValueError(f"layers {layer_id} and {sorted(clash)[0]} cannot be combined")


def _base_mode(base: str) -> GameMode:
    module_name, attr = _BASE_FACTORIES[base]
    import importlib

    factory = getattr(importlib.import_module(module_name), attr)
    return factory()


BASE_LABELS: dict[str, str] = {
    "chess": "Классика",
    "minichess": "Мини-шахматы",
    "shogi": "Сёги",
    "kyoto_shogi": "Киото-сёги",
    "dobutsu_shogi": "Добуцу-сёги",
    "hasami_shogi": "Хасами сёги",
    "reversi": "Реверси",
    "corners": "Уголки",
    "draughts": "Русские шашки",
    "nanai_checkers": "Нанайские шашки",
    "gobblet": "Gobblet Gobblers",
}


def family_for_base(base: str) -> str:
    for family_id, bases in FAMILY_BASES.items():
        if base in bases:
            return family_id
    return "chess"


def spec_display_name(spec: ModeSpec) -> str:
    if not spec.layers:
        return BASE_LABELS.get(spec.base, spec.base)
    parts = [LAYERS[layer_id].label for layer_id in OVERLAY_ORDER if layer_id in spec.layers]
    if spec.base != "chess":
        parts.insert(0, BASE_LABELS.get(spec.base, spec.base))
    return " · ".join(parts) or BASE_LABELS.get(spec.base, spec.base)


def _extras(mode: GameMode, **updates: object) -> dict[str, object]:
    extras = dict(mode.initial_extras)
    extras.update(updates)
    return extras


def _has_blocker_step(mode: GameMode) -> bool:
    return any(step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps)


def _victory_kinds(mode: GameMode) -> set[VictoryKind]:
    conditions = mode.victory if isinstance(mode.victory, tuple) else (mode.victory,)
    return {item.kind for item in conditions if isinstance(item, VictoryCondition)}


def _apply_giveaway(mode: GameMode) -> GameMode:
    from chess_core.modes.giveaway_rules import MustCaptureLegality

    return replace(
        mode,
        victory=VictoryCondition(VictoryKind.MATERIAL, lose_on_no_legal_moves=False),
        legality=MustCaptureLegality(),
        checks_enabled=False,
        initial_extras=_extras(
            mode,
            castling_rights=set(),
            promote_includes_king=True,
            empty_side_wins=True,
            blocked_side_wins=True,
        ),
    )


def _apply_fairy(mode: GameMode) -> GameMode:
    """Fairytale file-movement, or Fairy Duck king-capture when Duck is on."""
    from chess_core.modes.fairytale_rules import FairytaleFileResolver

    extras = _extras(mode, fairy_rules=True)
    if _has_blocker_step(mode):
        # Duck + Fairy → Fairy-Stockfish ALLVARS rules (no file resolver).
        extras["fairy_duck_rules"] = True
        victory = mode.victory
        if VictoryKind.MATERIAL not in _victory_kinds(mode):
            victory = VictoryCondition(VictoryKind.KING_CAPTURE)
        return replace(
            mode,
            checks_enabled=False,
            victory=victory,
            initial_extras=extras,
        )
    return replace(
        mode,
        move_resolver=FairytaleFileResolver(mode.pieces),
        initial_extras=extras,
    )


def _apply_cylindrical(mode: GameMode) -> GameMode:
    from chess_core.core.masks import MaskTableLoader
    from chess_core.core.topology import CylindricalFilesTopology
    from chess_core.infra.paths import masks_dir

    shape = mode.board.shape
    topology = CylindricalFilesTopology(shape)
    ray_table = mode.ray_table
    if shape.files == 8 and shape.ranks == 8:
        path = masks_dir() / "cylinder_8x8.json"
        if path.is_file():
            ray_table = MaskTableLoader().load(path)
    return replace(mode, topology=topology, ray_table=ray_table)


def _apply_duck(mode: GameMode) -> GameMode:
    if _has_blocker_step(mode):
        return mode
    steps = mode.turn_scenario.steps
    scenario = TurnScenario((*steps, TurnStep(StepKind.PLACE_BLOCKER, label="duck")))
    return replace(mode, turn_scenario=scenario)


def _apply_crazyhouse(mode: GameMode) -> GameMode:
    from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule

    if mode.drop_rule is not None and mode.capture_sink is CaptureSink.MOVER_HAND:
        return mode
    steps = mode.turn_scenario.steps
    if steps and steps[0].kind is StepKind.MOVE_OR_CAPTURE:
        steps = (TurnStep(StepKind.MOVE_OR_DROP), *steps[1:])
    elif not any(step.kind in {StepKind.MOVE_OR_DROP, StepKind.DROP} for step in steps):
        steps = (TurnStep(StepKind.MOVE_OR_DROP), *steps)
    return replace(
        mode,
        turn_scenario=TurnScenario(steps),
        drop_rule=CrazyhouseDropRule(),
        capture_sink=CaptureSink.MOVER_HAND,
    )


def _apply_chess960(mode: GameMode) -> GameMode:
    import random

    from chess_core.core.chess960 import chess960_rook_files, chess960_start_cells, decode_chess960_back_rank

    chosen = random.randrange(960)
    back_rank = decode_chess960_back_rank(chosen)
    extras = _extras(
        mode,
        castling_rights={"K", "Q", "k", "q"},
        castling_rooks=chess960_rook_files(back_rank),
        chess960_position=chosen,
    )
    return replace(mode, start_cells=chess960_start_cells(chosen), initial_extras=extras)


def _apply_bughouse(mode: GameMode) -> GameMode:
    from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule

    steps = mode.turn_scenario.steps
    if steps and steps[0].kind is StepKind.MOVE_OR_CAPTURE:
        steps = (TurnStep(StepKind.MOVE_OR_DROP), *steps[1:])
    return replace(
        mode,
        turn_scenario=TurnScenario(steps),
        drop_rule=CrazyhouseDropRule(),
        capture_sink=CaptureSink.PARTNER_OUTBOUND,
        initial_extras=_extras(mode, match_kind="bughouse", board_count=2),
    )


def _apply_hand_and_brain(mode: GameMode) -> GameMode:
    return replace(mode, initial_extras=_extras(mode, match_kind="hand_and_brain"))


_CHESSY = frozenset({"chess", "minichess"})
_CHESS_8 = frozenset({"chess"})

LAYERS: dict[str, ModeLayer] = {
    "giveaway": ModeLayer(
        "giveaway",
        "Giveaway",
        applies_to=_CHESSY,
        apply=_apply_giveaway,
    ),
    "fairy": ModeLayer(
        "fairy",
        "Fairytale",
        applies_to=_CHESSY,
        apply=_apply_fairy,
    ),
    "cylindrical": ModeLayer(
        "cylindrical",
        "Цилиндрические",
        applies_to=_CHESS_8,
        apply=_apply_cylindrical,
    ),
    "duck": ModeLayer(
        "duck",
        "Duck chess",
        applies_to=_CHESSY,
        conflicts=frozenset({"bughouse", "hand_and_brain"}),
        apply=_apply_duck,
    ),
    "crazyhouse": ModeLayer(
        "crazyhouse",
        "Crazyhouse",
        applies_to=_CHESS_8,
        conflicts=frozenset({"bughouse"}),
        apply=_apply_crazyhouse,
    ),
    "chess960": ModeLayer(
        "chess960",
        "Chess960",
        applies_to=_CHESS_8,
        apply=_apply_chess960,
    ),
    "bughouse": ModeLayer(
        "bughouse",
        "Bughouse",
        applies_to=_CHESS_8,
        conflicts=frozenset({"duck", "hand_and_brain", "crazyhouse"}),
        apply=_apply_bughouse,
    ),
    "hand_and_brain": ModeLayer(
        "hand_and_brain",
        "Hand & Brain",
        applies_to=_CHESS_8,
        conflicts=frozenset({"duck", "bughouse"}),
        apply=_apply_hand_and_brain,
    ),
}

_APPLY_ORDER: tuple[str, ...] = (
    "chess960",
    "cylindrical",
    "crazyhouse",
    "bughouse",
    "hand_and_brain",
    "duck",
    "fairy",
    "giveaway",
)

OVERLAY_ORDER: tuple[str, ...] = (
    "giveaway",
    "fairy",
    "cylindrical",
    "duck",
    "crazyhouse",
    "chess960",
    "bughouse",
    "hand_and_brain",
)
