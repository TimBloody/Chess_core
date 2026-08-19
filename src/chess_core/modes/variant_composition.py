"""Declarative modifier registry and chess-family mode composition."""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from chess_core.core.board import BoardShape
from chess_core.core.chess960 import (
    Chess960CastlingRule,
    chess960_rook_files,
    chess960_start_cells,
    scharnagl_back_rank,
)
from chess_core.core.gamemode import GameMode, GameModeBuilder
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.core.turn import StepKind, TurnScenario, TurnStep
from chess_core.modes.crazyhouse_rules import CrazyhouseDropRule
from chess_core.modes.fairytale_rules import FairytaleFileResolver
from chess_core.modes.koth_rules import center_zone_mask
from chess_core.modes.three_check_rules import ThreeCheckCounter
from chess_core.modes.two_move_rules import DoubleMoveTurnPolicy


class ModifierAxis(Enum):
    """Mechanic axis; victory modifiers are additive, others are exclusive."""

    VICTORY = auto()
    MOVEMENT = auto()
    TURN = auto()
    SETUP = auto()
    TOPOLOGY = auto()
    DROPS = auto()


@dataclass(frozen=True, slots=True)
class VariantModifier:
    """Description of one composable ruleset modifier."""

    id: str
    name: str
    axis: ModifierAxis
    description: str
    implemented: bool = False
    additive: bool = False


CHESS960 = VariantModifier(
    id="chess960",
    name="Chess960",
    axis=ModifierAxis.SETUP,
    description="Fischer random starting position (Scharnagl ids 0..959).",
    implemented=True,
)

CYLINDRICAL = VariantModifier(
    id="cylindrical",
    name="Cylindrical",
    axis=ModifierAxis.TOPOLOGY,
    description="Files a and h are adjacent (cylindrical board topology).",
    implemented=True,
)

CRAZYHOUSE = VariantModifier(
    id="crazyhouse",
    name="Crazyhouse",
    axis=ModifierAxis.DROPS,
    description="Captured pieces return to hand and may be dropped instead of moving.",
    implemented=True,
)

DUCK = VariantModifier(
    id="duck",
    name="Duck",
    axis=ModifierAxis.TURN,
    description=(
        "After each move, place the duck blocker; king capture wins; stalemate wins "
        "for the blocked side."
    ),
    implemented=True,
)

THREE_CHECK = VariantModifier(
    id="three_check",
    name="Three-check",
    axis=ModifierAxis.VICTORY,
    description=(
        "Additional win: deliver three checks to the opponent. "
        "Checkmate remains a win."
    ),
    additive=True,
    implemented=True,
)

KING_OF_THE_HILL = VariantModifier(
    id="king_of_the_hill",
    name="King of the Hill",
    axis=ModifierAxis.VICTORY,
    description=(
        "Additional win: royal piece safely reaches one of the four central "
        "squares (d4, e4, d5, e5 on 8x8)."
    ),
    additive=True,
    implemented=True,
)

FAIRYTALE = VariantModifier(
    id="fairytale",
    name="Fairytale",
    axis=ModifierAxis.MOVEMENT,
    description=(
        "Pawns, queens and kings move normally. Rooks, bishops and knights "
        "move like the piece type that starts on their current file: "
        "a/h rook, b/g knight, c/f bishop; on d/e they keep their own type."
    ),
    implemented=True,
)

TWO_MOVE = VariantModifier(
    id="two_move",
    name="Two-move",
    axis=ModifierAxis.TURN,
    description=(
        "White opens with one move. Then each side normally plays two moves "
        "in sequence; if the first move gives check, the turn ends and the "
        "opponent moves. If a player starts their turn in check, they make "
        "only one move."
    ),
    implemented=True,
)

CANONICAL_MODIFIER_ORDER: tuple[str, ...] = (
    CHESS960.id,
    CYLINDRICAL.id,
    CRAZYHOUSE.id,
    DUCK.id,
    TWO_MOVE.id,
    FAIRYTALE.id,
    THREE_CHECK.id,
    KING_OF_THE_HILL.id,
)

CHESS_FAMILY_PRESETS: dict[str, tuple[str, ...]] = {
    "chess960": (CHESS960.id,),
    "cylindrical": (CYLINDRICAL.id,),
    "crazyhouse": (CRAZYHOUSE.id,),
    "duck": (DUCK.id,),
    "two_move": (TWO_MOVE.id,),
    "fairytale": (FAIRYTALE.id,),
    "three_check": (THREE_CHECK.id,),
    "king_of_the_hill": (KING_OF_THE_HILL.id,),
    "three_check_king_of_the_hill": (THREE_CHECK.id, KING_OF_THE_HILL.id),
}

CHESS_FAMILY_MODE_IDS: frozenset[str] = frozenset(
    {"chess", *CHESS_FAMILY_PRESETS.keys()}
)

_BUILTIN_MODIFIERS: dict[str, VariantModifier] = {
    modifier.id: modifier
    for modifier in (
        CHESS960,
        CYLINDRICAL,
        CRAZYHOUSE,
        DUCK,
        THREE_CHECK,
        KING_OF_THE_HILL,
        FAIRYTALE,
        TWO_MOVE,
    )
}


def modifier_registry() -> dict[str, VariantModifier]:
    return dict(_BUILTIN_MODIFIERS)


def get_modifier(modifier_id: str) -> VariantModifier:
    try:
        return _BUILTIN_MODIFIERS[modifier_id]
    except KeyError:
        raise ValueError(f"unknown variant modifier: {modifier_id}") from None


def canonical_modifier_ids(modifier_ids: tuple[str, ...]) -> tuple[str, ...]:
    """Sort modifier ids into the stable composed-mode order."""
    selected = frozenset(modifier_ids)
    return tuple(modifier_id for modifier_id in CANONICAL_MODIFIER_ORDER if modifier_id in selected)


def modifier_descriptions(modifier_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(get_modifier(modifier_id).description for modifier_id in modifier_ids)


def validate_modifier_combination(modifier_ids: tuple[str, ...]) -> None:
    """Reject unknown ids, axis conflicts, and duck vs check-based modifiers."""
    if not modifier_ids:
        raise ValueError("at least one modifier id is required")

    seen_exclusive: dict[ModifierAxis, str] = {}
    modifier_set = frozenset(modifier_ids)
    for modifier_id in modifier_ids:
        modifier = get_modifier(modifier_id)
        if modifier.axis is ModifierAxis.VICTORY:
            if not modifier.additive:
                raise ValueError(
                    f"victory modifier {modifier_id} must be marked additive"
                )
            continue
        previous = seen_exclusive.get(modifier.axis)
        if previous is not None:
            raise ValueError(
                f"modifiers {previous} and {modifier_id} conflict on "
                f"{modifier.axis.name} axis"
            )
        seen_exclusive[modifier.axis] = modifier_id

    if DUCK.id in modifier_set and THREE_CHECK.id in modifier_set:
        raise ValueError(
            f"modifiers {DUCK.id} and {THREE_CHECK.id} conflict (no checks in duck chess)"
        )


def compose_modifier_name(modifier_ids: tuple[str, ...]) -> str:
    validate_modifier_combination(modifier_ids)
    return " + ".join(get_modifier(modifier_id).name for modifier_id in modifier_ids)


def parse_modifier_ids_from_mode_id(mode_id: str) -> tuple[str, ...]:
    """Extract modifier ids from a preset or composed chess-family mode id."""
    if mode_id == "chess":
        return ()
    if mode_id in CHESS_FAMILY_PRESETS:
        return CHESS_FAMILY_PRESETS[mode_id]
    if mode_id.startswith("chess+"):
        raw = mode_id.split("+", 1)[1]
        if not raw:
            return ()
        modifier_ids = tuple(part for part in raw.split("+") if part)
        return canonical_modifier_ids(modifier_ids)
    return ()


def resolve_chess_mode_id(modifier_ids: tuple[str, ...]) -> str:
    """Map modifiers to a named preset id or a composed ``chess+...`` id."""
    canonical = canonical_modifier_ids(modifier_ids)
    for preset_id, preset_modifiers in CHESS_FAMILY_PRESETS.items():
        if canonical == preset_modifiers:
            return preset_id
    if not canonical:
        return "chess"
    return "chess+" + "+".join(canonical)


def compose_chess_mode(
    modifier_ids: tuple[str, ...],
    *,
    chess960_id: int | None = None,
    mode_id: str | None = None,
    name: str | None = None,
) -> GameMode:
    """Build a playable chess-family mode by applying modifier ids to classic chess."""
    canonical = canonical_modifier_ids(modifier_ids)
    validate_modifier_combination(canonical)
    modifier_set = frozenset(canonical)

    composed_id = mode_id or (
        "chess+" + "+".join(canonical) if canonical else "chess"
    )
    display_name = name
    if display_name is None and CHESS960.id in modifier_set:
        chosen_preview = chess960_id if chess960_id is not None else 518
        if len(canonical) == 1:
            display_name = f"Chess960 #{chosen_preview}"
        else:
            other_name = compose_modifier_name(
                tuple(modifier for modifier in canonical if modifier != CHESS960.id)
            )
            display_name = f"Chess960 #{chosen_preview} + {other_name}"
    if display_name is None:
        display_name = compose_modifier_name(canonical)
    any_unimplemented = any(
        not get_modifier(modifier_id).implemented for modifier_id in canonical
    )

    from chess_core.modes.chess import _chess_builder

    topology = None
    if CYLINDRICAL.id in modifier_set:
        topology = CylindricalFilesTopology(BoardShape(files=8, ranks=8))
    builder = _chess_builder(composed_id, display_name, topology=topology)
    extras: dict[str, object] = {"castling_rights": {"K", "Q", "k", "q"}}

    if CHESS960.id in modifier_set:
        chosen = chess960_id if chess960_id is not None else random.randrange(960)
        back_rank = scharnagl_back_rank(chosen)
        builder.with_start_cells(chess960_start_cells(chosen))
        builder.with_castling_rule(Chess960CastlingRule(chess960_rook_files(back_rank)))
        extras["chess960_position"] = chosen

    if CRAZYHOUSE.id in modifier_set:
        builder.with_drop_rule(CrazyhouseDropRule())

    if THREE_CHECK.id in modifier_set:
        extras["checks_given"] = {"white": 0, "black": 0}

    builder.with_initial_extras(extras)
    builder.with_victory(_victory_for_modifiers(modifier_set))
    _apply_turn_rules(builder, modifier_set)
    _apply_movement_rules(builder, modifier_set)
    _apply_state_transitions(builder, modifier_set)

    return (
        builder.with_is_dummy(any_unimplemented)
        .with_modifier_ids(canonical)
        .build()
    )


def compose_dummy_chess_mode(
    mode_id: str,
    modifier_ids: tuple[str, ...],
    *,
    name: str | None = None,
    builder_factory: Callable[[], GameModeBuilder],
) -> GameMode:
    """Build a dummy chess mode from additive/exclusive modifier ids."""
    validate_modifier_combination(modifier_ids)
    display_name = name or compose_modifier_name(modifier_ids)
    any_unimplemented = any(
        not get_modifier(modifier_id).implemented for modifier_id in modifier_ids
    )
    return (
        builder_factory()
        .with_is_dummy(any_unimplemented)
        .with_modifier_ids(modifier_ids)
        .build()
    )


def _victory_for_modifiers(
    modifier_set: frozenset[str],
) -> VictoryCondition | tuple[VictoryCondition, ...]:
    conditions: list[VictoryCondition] = []
    if DUCK.id in modifier_set:
        conditions.append(
            VictoryCondition(VictoryKind.KING_CAPTURE, lose_on_no_legal_moves=False)
        )
    else:
        conditions.append(VictoryCondition(VictoryKind.CHECKMATE))

    if KING_OF_THE_HILL.id in modifier_set:
        conditions.append(
            VictoryCondition(
                VictoryKind.KING_REACHES_ZONE,
                target_zone_mask=center_zone_mask(),
            )
        )

    if THREE_CHECK.id in modifier_set:
        conditions.append(VictoryCondition(VictoryKind.THREE_CHECK, threshold=3))

    if len(conditions) == 1:
        return conditions[0]
    return tuple(conditions)


def _move_step(modifier_set: frozenset[str]) -> StepKind:
    if CRAZYHOUSE.id in modifier_set:
        return StepKind.MOVE_OR_DROP
    return StepKind.MOVE_OR_CAPTURE


def _apply_turn_rules(builder: GameModeBuilder, modifier_set: frozenset[str]) -> None:
    move_kind = _move_step(modifier_set)
    if DUCK.id in modifier_set:
        builder.with_turn_scenario(
            TurnScenario(
                (
                    TurnStep(move_kind, label="move"),
                    TurnStep(StepKind.PLACE_BLOCKER, label="duck"),
                )
            )
        )
        return

    if TWO_MOVE.id in modifier_set:
        builder.with_turn_policy(DoubleMoveTurnPolicy())
        builder.with_turn_scenario(
            TurnScenario(
                (
                    TurnStep(move_kind, label="move 1"),
                    TurnStep(move_kind, label="move 2"),
                )
            )
        )
        return

    if CRAZYHOUSE.id in modifier_set:
        builder.with_turn_scenario(TurnScenario((TurnStep(move_kind),)))


def _apply_movement_rules(builder: GameModeBuilder, modifier_set: frozenset[str]) -> None:
    if FAIRYTALE.id in modifier_set:
        builder.with_move_resolver(FairytaleFileResolver())


def _apply_state_transitions(
    builder: GameModeBuilder, modifier_set: frozenset[str]
) -> None:
    if THREE_CHECK.id in modifier_set:
        builder.with_transitions((ThreeCheckCounter(),))
