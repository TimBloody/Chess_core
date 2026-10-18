"""Cell tokenizer: role sequence → SAN. Full grammar layers A–D are P3."""

from __future__ import annotations

from typing import Sequence

from chess_core.ocr.roles import glyphs_to_san, roles_to_san


class CellDecoder:
    """notation_mode is constructor state, not a branch scattered through the pipeline."""

    def __init__(self, notation_mode: str = "ru") -> None:
        if notation_mode not in {"ru", "en"}:
            raise ValueError(f"notation_mode must be 'ru' or 'en', got {notation_mode!r}")
        self.notation_mode = notation_mode

    def decode_roles(self, roles: Sequence[str]) -> str:
        return roles_to_san(roles, notation_mode=self.notation_mode)

    def decode_glyphs(self, chars: Sequence[str]) -> str:
        return glyphs_to_san(chars, notation_mode=self.notation_mode)
