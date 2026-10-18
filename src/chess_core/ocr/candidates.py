"""Top-k move candidates handed to a later sheet-pair / search step.

Legal flags are attached beside the raw string. They do not drop or reorder it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.move_norm import normalize_move_text, original_ink
from chess_core.ocr.roles import ROLE_BY_ID


@dataclass(frozen=True, slots=True)
class MoveCandidate:
    raw: str
    normalized: str
    log_score: float
    roles: tuple[str, ...] = ()
    legal: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "log_score": self.log_score,
            "roles": list(self.roles),
            "legal": self.legal,
        }


@dataclass(frozen=True, slots=True)
class CellCandidateList:
    """One cell, ready for a later ply match. Search is not applied here."""

    sheet_id: str
    ply_index: int | None
    source_cell: str
    notation_mode: str
    candidates: tuple[MoveCandidate, ...]
    uncertainty: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "sheet_id": self.sheet_id,
            "ply_index": self.ply_index,
            "source_cell": self.source_cell,
            "notation_mode": self.notation_mode,
            "candidates": [item.to_dict() for item in self.candidates],
            "uncertainty": list(self.uncertainty),
        }


def ensure_sorted(candidates: Sequence[MoveCandidate]) -> tuple[MoveCandidate, ...]:
    scores = [item.log_score for item in candidates]
    if scores != sorted(scores, reverse=True):
        raise ValueError("top-k must be sorted by log_score descending")
    return tuple(candidates)


def attach_legality(
    candidates: Sequence[MoveCandidate],
    legal: Sequence[bool | None],
) -> tuple[MoveCandidate, ...]:
    """Keep every raw candidate. Legality is a flag, not a filter."""

    rows = tuple(candidates)
    flags = tuple(legal)
    if len(rows) != len(flags):
        raise ValueError("legality flags must align with candidates")
    return tuple(replace(row, legal=flag) for row, flag in zip(rows, flags))


def scored_from_glyphs(
    glyphs: Sequence[Mapping[str, object]],
    decoder: CellDecoder,
    *,
    k: int,
) -> tuple[MoveCandidate, ...]:
    """Beam over stored per-glyph alternatives. Does not call the network."""

    if not glyphs or k < 1:
        return ()
    beams: list[tuple[tuple[str, ...], float]] = [((), 0.0)]
    for glyph in glyphs:
        alts = glyph.get("alts") or ()
        ranked = [
            (str(name), float(score))
            for name, score in alts
            if str(name) in ROLE_BY_ID
        ]
        if not ranked:
            role = str(glyph.get("role") or glyph.get("char") or "")
            if role in ROLE_BY_ID:
                ranked = [(role, float(glyph.get("score") or 0.0))]
        ranked = ranked[:k]
        if not ranked:
            continue
        nxt: list[tuple[tuple[str, ...], float]] = []
        for prefix, mass in beams:
            for role, score in ranked:
                nxt.append((prefix + (role,), mass + math.log(max(score, 1e-8))))
        nxt.sort(key=lambda item: -item[1])
        beams = nxt[:40]
    found: list[MoveCandidate] = []
    seen: set[str] = set()
    for roles, log_score in beams:
        raw = decoder.decode_roles(roles)
        if raw in seen:
            continue
        seen.add(raw)
        found.append(
            MoveCandidate(
                raw=original_ink(raw),
                normalized=normalize_move_text(raw),
                log_score=log_score,
                roles=roles,
            )
        )
        if len(found) >= k:
            break
    return ensure_sorted(found)
