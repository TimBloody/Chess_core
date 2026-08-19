import pytest

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.modes.checkers import compose_checkers_mode, resolve_checkers_mode_id
from chess_core.modes.checkers_rules import CheckersOptions


def test_family_resolver_encodes_all_flag_combinations() -> None:
    register_builtin_modes()
    default_on = resolve_checkers_mode_id("checkers")
    assert default_on.initial_extras["checkers_options"] == CheckersOptions()

    none = resolve_checkers_mode_id("checkers+none")
    assert none.initial_extras["checkers_options"] == CheckersOptions(
        mandatory_capture=False,
        backward_capture=False,
        flying_king=False,
    )

    flying = default_registry.get("checkers+flying_king")
    options = flying.initial_extras["checkers_options"]
    assert options == CheckersOptions(
        mandatory_capture=False,
        backward_capture=False,
        flying_king=True,
    )


def test_unknown_modifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown checkers modifier"):
        compose_checkers_mode(("duck",))
    with pytest.raises(ValueError, match="none"):
        compose_checkers_mode(("none",))
