import pytest

from chess_core.core.rules import VictoryKind
from chess_core.core.topology import CylindricalFilesTopology
from chess_core.core.turn import StepKind
from chess_core.modes.giveaway_rules import MustCaptureLegality
from chess_core.modes.orchestrator import (
    compose_mode,
    parse_spec,
    toggle_layer,
)


def test_giveaway_plus_fairy_keeps_antichess_victory() -> None:
    spec = parse_spec("giveaway+fairy")
    assert spec.base == "chess"
    assert spec.layers == frozenset({"giveaway", "fairy"})
    assert spec.encoded() == "chess+fairy+giveaway"

    mode = compose_mode("giveaway+fairytale")
    kinds = {item.kind for item in (mode.victory if isinstance(mode.victory, tuple) else (mode.victory,))}
    assert VictoryKind.MATERIAL in kinds
    assert mode.checks_enabled is False
    assert isinstance(mode.legality, MustCaptureLegality)
    assert mode.initial_extras.get("fairy_rules") is True
    assert mode.move_resolver is not None
    assert mode.id == "chess+fairy+giveaway"


def test_giveaway_plus_cylindrical_wraps_files() -> None:
    mode = compose_mode("chess+cylindrical+giveaway")
    assert isinstance(mode.topology, CylindricalFilesTopology)
    assert isinstance(mode.legality, MustCaptureLegality)
    assert mode.checks_enabled is False


def test_duck_plus_fairy_sets_king_capture_and_blocker() -> None:
    mode = compose_mode("chess+duck+fairy")
    assert any(step.kind is StepKind.PLACE_BLOCKER for step in mode.turn_scenario.steps)
    assert mode.initial_extras.get("fairy_duck_rules") is True
    kinds = {item.kind for item in (mode.victory if isinstance(mode.victory, tuple) else (mode.victory,))}
    assert VictoryKind.KING_CAPTURE in kinds
    assert mode.checks_enabled is False


def test_shogi_plus_giveaway_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not apply"):
        compose_mode("shogi+giveaway")


def test_preset_alias_round_trip() -> None:
    assert parse_spec("giveaway").encoded() == "giveaway"
    assert parse_spec("duck").encoded() == "duck"
    assert parse_spec("chess+giveaway").encoded() == "giveaway"


def test_toggle_layer_drops_conflicting_duck() -> None:
    spec = parse_spec("duck")
    combined = toggle_layer(spec, "bughouse", True)
    assert "duck" not in combined.layers
    assert "bughouse" in combined.layers
