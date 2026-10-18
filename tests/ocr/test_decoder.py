"""P1 cell decoder: KN+ER king, notation_mode, castle, case, markers."""

from __future__ import annotations

from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.hypothesis import MISSING_MOVE
from chess_core.ocr.roles import format_ru, glyphs_to_san, restore_case, roles_to_san


def test_kf3_ru_is_knight_en_is_king() -> None:
    ru = CellDecoder("ru")
    en = CellDecoder("en")
    assert ru.decode_glyphs(tuple("Кf3")) == "Nf3"
    assert en.decode_glyphs(tuple("Kf3")) == "Kf3"
    assert glyphs_to_san(tuple("Kрe2"), notation_mode="ru") == "Ke2"
    assert format_ru("Ke2") == "Крe2"


def test_castle_zero_and_o_fold() -> None:
    decoder = CellDecoder("ru")
    assert decoder.decode_glyphs(tuple("0-0")) == "O-O"
    assert decoder.decode_glyphs(tuple("O-O")) == "O-O"
    assert decoder.decode_glyphs(tuple("О-О")) == "O-O"
    assert decoder.decode_roles(("O", "O", "O")) == "O-O-O"
    assert format_ru("O-O") == "0-0"


def test_restore_case_file_lower_piece_upper() -> None:
    assert restore_case("f_a", "file") == "a"
    assert restore_case("f_c", "file") == "c"
    assert restore_case("KN", "piece") == "N"
    assert restore_case("BS", "piece") == "B"
    assert restore_case("RK", "piece") == "R"
    text = roles_to_san(("BS", "f_e", "r_7"), notation_mode="ru")
    assert text[0].isupper()
    assert "e" in text
    assert text == "Be7"


def test_markers_do_not_become_missing() -> None:
    assert roles_to_san(("f_e", "r_4", "PLUS")) == "e4+"
    assert roles_to_san(("f_e", "r_8", "HASH")) == "e8#"
    assert roles_to_san(("f_e", "r_8", "EQ", "QN")) == "e8=Q"
    assert roles_to_san(("PLUS",)) == "+"
    assert roles_to_san(("HASH",)) == "#"
    assert roles_to_san(("EQ",)) == "="
    assert roles_to_san(()) == MISSING_MOVE
    assert roles_to_san(()) != ""
