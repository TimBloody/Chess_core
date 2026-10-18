"""P1 class-space invariants: 26 roles, disjoint glyphs, Кр is two glyphs."""

from __future__ import annotations

from chess_core.ocr.roles import (
    KNOWN_VISUAL_NEAR_MISSES,
    N_ROLES,
    ROLE_IDS,
    ROLES,
    canonicalize,
    kr_roles,
    parse_roles,
    serialize_roles,
    split_kr,
)


def test_exactly_twenty_six_roles() -> None:
    assert N_ROLES == 26
    assert len(ROLES) == 26
    assert len(ROLE_IDS) == 26
    assert len(set(ROLE_IDS)) == 26


def test_no_empty_accepted_glyphs() -> None:
    for role in ROLES:
        assert role.accepted_glyphs, role.id


def test_glyph_to_role_is_injective() -> None:
    # Latin b (file) and latin B (bishop) are different code points, so they
    # do not collide here. They are a visual near-miss (f_b vs BS), measured
    # in role_confusion, not merged.
    seen: dict[str, str] = {}
    for role in ROLES:
        for glyph in role.accepted_glyphs:
            assert glyph not in seen, f"{glyph!r} in {seen[glyph]} and {role.id}"
            seen[glyph] = role.id
    assert canonicalize("b") == "f_b"
    assert canonicalize("B") == "BS"
    assert canonicalize("c") == "f_c"
    assert canonicalize("C") == "BS"
    assert ("f_b", "BS") in KNOWN_VISUAL_NEAR_MISSES


def test_kr_is_exactly_two_glyphs() -> None:
    pair = kr_roles()
    assert pair == ("KN", "ER")
    assert split_kr(("KN", "ER", "f_e", "r_2")) == ("KN+ER", "f_e", "r_2")
    assert serialize_roles(pair) == "KN ER"
    assert parse_roles("KN ER") == pair
    rebuilt = parse_roles(serialize_roles(pair))
    assert rebuilt == pair
    assert canonicalize("К") == "KN"
    assert canonicalize("р") == "ER"


def test_zero_and_o_share_castle_role() -> None:
    assert canonicalize("0") == "O"
    assert canonicalize("O") == "O"
    assert canonicalize("О") == "O"
