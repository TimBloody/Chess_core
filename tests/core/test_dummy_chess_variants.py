import pytest

from chess_core.core.movegen import MoveGenerator
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.chess import (
    fairytale_chess,
    king_of_the_hill,
    three_check_chess,
    three_check_king_of_the_hill,
    two_move_chess,
)
from chess_core.modes.variant_composition import (
    FAIRYTALE,
    KING_OF_THE_HILL,
    THREE_CHECK,
    TWO_MOVE,
    compose_modifier_name,
    get_modifier,
    modifier_descriptions,
    validate_modifier_combination,
)


def _assert_classic_start(mode) -> None:
    state = mode.initial_state()
    assert mode.board.shape.cell_count == 64
    assert sum(piece is not None for piece in state.board_state.cells.values()) == 32
    assert mode.ray_table is not None
    assert mode.promotion_rule is not None
    assert len(MoveGenerator(mode).generate_legal(state)) == 20


@pytest.mark.parametrize(
    ("factory", "mode_id", "modifier_id"),
    [
        (two_move_chess, "two_move", TWO_MOVE.id),
        (fairytale_chess, "fairytale", FAIRYTALE.id),
        (three_check_chess, "three_check", THREE_CHECK.id),
        (king_of_the_hill, "king_of_the_hill", KING_OF_THE_HILL.id),
    ],
)
def test_dummy_variant_factories_are_registered_and_classic_playable(
    factory, mode_id, modifier_id
) -> None:
    mode = factory()
    assert mode.id == mode_id
    assert not mode.is_dummy
    assert mode.modifier_ids == (modifier_id,)
    assert mode.modifier_ids[0] == get_modifier(modifier_id).id
    assert get_modifier(modifier_id).implemented
    _assert_classic_start(mode)


def test_dummy_variant_modifier_descriptions_match_registry() -> None:
    mode = fairytale_chess()
    descriptions = modifier_descriptions(mode.modifier_ids)
    assert descriptions == (FAIRYTALE.description,)
    assert descriptions[0] == FAIRYTALE.description


def test_three_check_and_king_of_the_hill_compose() -> None:
    mode = three_check_king_of_the_hill()
    assert not mode.is_dummy
    assert mode.modifier_ids == (THREE_CHECK.id, KING_OF_THE_HILL.id)
    assert compose_modifier_name(mode.modifier_ids) == "Three-check + King of the Hill"
    _assert_classic_start(mode)


def test_validate_modifier_combination_rejects_exclusive_axis_conflict() -> None:
    with pytest.raises(ValueError, match="conflict on TURN axis"):
        validate_modifier_combination((TWO_MOVE.id, TWO_MOVE.id))


def test_validate_modifier_combination_rejects_unknown_modifier() -> None:
    with pytest.raises(ValueError, match="unknown variant modifier"):
        validate_modifier_combination(("not_a_modifier",))


def test_builtin_registry_lists_new_dummy_modes() -> None:
    register_builtin_modes()
    mode_ids = default_registry.list_modes()
    for mode_id in (
        "two_move",
        "fairytale",
        "three_check",
        "king_of_the_hill",
        "three_check_king_of_the_hill",
    ):
        assert mode_id in mode_ids
        mode = default_registry.get(mode_id)
        assert not mode.is_dummy
        assert mode.modifier_ids
