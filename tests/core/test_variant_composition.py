import os

import pytest

from chess_core.core.registry import default_registry
from chess_core.core.rules import VictoryKind
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.modes import register_builtin_modes
from chess_core.modes.variant_composition import (
    compose_chess_mode,
    validate_modifier_combination,
)


def test_compose_chess960_three_check_has_position_extra_and_victory() -> None:
    mode = compose_chess_mode(("chess960", "three_check"), chess960_id=518)
    assert mode.initial_extras.get("chess960_position") == 518
    assert VictoryKind.THREE_CHECK in mode.victory_kinds()
    assert mode.initial_extras.get("checks_given") == {"white": 0, "black": 0}
    assert not mode.is_dummy


def test_compose_cylindrical_koth_has_topology_and_zone_victory() -> None:
    mode = compose_chess_mode(("cylindrical", "king_of_the_hill"))
    assert isinstance(mode.topology, CylindricalFilesTopology)
    assert VictoryKind.KING_REACHES_ZONE in mode.victory_kinds()
    zone_condition = next(
        condition
        for condition in mode.victory_conditions()
        if condition.kind is VictoryKind.KING_REACHES_ZONE
    )
    assert zone_condition.target_zone_mask is not None
    assert not mode.is_dummy


def test_compose_crazyhouse_fairytale_has_drop_rule_and_resolver() -> None:
    mode = compose_chess_mode(("crazyhouse", "fairytale"))
    assert mode.drop_rule is not None
    assert mode.move_resolver is not None
    assert not mode.is_dummy


def test_compose_duck_two_move_raises() -> None:
    with pytest.raises(ValueError, match="conflict on TURN axis"):
        validate_modifier_combination(("duck", "two_move"))


def test_compose_duck_three_check_raises() -> None:
    with pytest.raises(ValueError, match="no checks in duck chess"):
        validate_modifier_combination(("duck", "three_check"))


def test_registry_resolves_composed_chess_three_check() -> None:
    register_builtin_modes()
    mode = default_registry.get("chess+three_check")
    assert VictoryKind.THREE_CHECK in mode.victory_kinds()
    assert mode.id == "chess+three_check"
    assert not mode.is_dummy


def test_compose_mode_id_canonical_order() -> None:
    mode = compose_chess_mode(
        ("king_of_the_hill", "three_check", "cylindrical"),
        mode_id="chess+cylindrical+three_check+king_of_the_hill",
    )
    assert mode.id == "chess+cylindrical+three_check+king_of_the_hill"
    assert mode.modifier_ids == (
        "cylindrical",
        "three_check",
        "king_of_the_hill",
    )
