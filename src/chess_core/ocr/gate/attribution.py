"""Error attribution and oracle@k. One category per gold cell, priority order."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.gold import GoldSheet
from chess_core.ocr.hypothesis import CellHypothesis
from chess_core.ocr.metrics import _castle_fold
from chess_core.ocr.roles import ROLE_BY_ID, try_canonicalize

CATEGORIES: tuple[str, ...] = (
    "GATE_FN",
    "SEG_MISS",
    "SEG_MERGE",
    "SEG_SPLIT",
    "CLS_MISS",
    "CLS_WRONG",
    "DECODER",
    "GRAMMAR",
    "OK",
)


@dataclass(frozen=True, slots=True)
class CellAttribution:
    category: str
    gold_ply: str
    raw: str
    legal: str
    n_gold_chars: int
    n_glyphs: int
    notes: str = ""


def gold_roles_for_cell(chars: Sequence[str]) -> tuple[str, ...]:
    roles = []
    for char in chars:
        role = try_canonicalize(char)
        if role is None:
            continue
        roles.append(role)
    return tuple(roles)


def _topk_roles(glyph: Mapping[str, Any], k: int) -> list[str]:
    alts = glyph.get("alts") or ()
    names = [str(item[0]) for item in alts if item]
    top = str(glyph.get("role") or glyph.get("char") or "")
    if top and top not in names:
        names.insert(0, top)
    return [name for name in names if name in ROLE_BY_ID][:k]


def assemble_candidates(
    glyphs: Sequence[Mapping[str, Any]],
    decoder: CellDecoder,
    *,
    k: int,
) -> list[str]:
    if not glyphs:
        return []
    beams: list[tuple[tuple[str, ...], float]] = [((), 1.0)]
    for glyph in glyphs:
        ranked = []
        alts = glyph.get("alts") or ()
        if not alts:
            role = str(glyph.get("role") or glyph.get("char") or "")
            score = float(glyph.get("score") or 0.0)
            if role in ROLE_BY_ID:
                ranked = [(role, score)]
        else:
            ranked = [(str(name), float(score)) for name, score in alts if str(name) in ROLE_BY_ID]
        ranked = ranked[: max(k, 1)]
        if not ranked:
            continue
        nxt: list[tuple[tuple[str, ...], float]] = []
        for prefix, mass in beams:
            for role, score in ranked:
                nxt.append((prefix + (role,), mass * max(float(score), 1e-6)))
        nxt.sort(key=lambda item: -item[1])
        beams = nxt[:40]
    texts = []
    seen = set()
    for roles, _mass in beams:
        text = decoder.decode_roles(roles)
        if text not in seen:
            seen.add(text)
            texts.append(text)
    return texts


def attribute_cell(
    *,
    gold_ply: str,
    gold_chars: Sequence[str],
    detail: Mapping[str, Any],
    hypothesis: CellHypothesis,
    decoder: CellDecoder,
) -> CellAttribution:
    gold_roles = gold_roles_for_cell(gold_chars)
    glyphs = list(detail.get("glyphs") or ())
    n_g = len(gold_roles)
    n_p = len(glyphs)
    raw = str(detail.get("raw") or hypothesis.raw or "")
    legal = hypothesis.text
    gate = bool(detail.get("gate_rejected") or hypothesis.gate_rejected)
    if gate and _castle_fold(raw) != _castle_fold(gold_ply) and _castle_fold(legal) != _castle_fold(gold_ply):
        return CellAttribution("GATE_FN", gold_ply, raw, legal, n_g, n_p, "gate dropped a gold cell")
    if n_p == 0:
        return CellAttribution("SEG_MISS", gold_ply, raw, legal, n_g, n_p)
    if n_g and n_p < n_g:
        return CellAttribution("SEG_MERGE", gold_ply, raw, legal, n_g, n_p)
    if n_g and n_p > n_g:
        return CellAttribution("SEG_SPLIT", gold_ply, raw, legal, n_g, n_p)
    if _castle_fold(raw) == _castle_fold(gold_ply):
        if _castle_fold(legal) == _castle_fold(gold_ply):
            return CellAttribution("OK", gold_ply, raw, legal, n_g, n_p)
        return CellAttribution("GRAMMAR", gold_ply, raw, legal, n_g, n_p, "raw matched gold, snap did not")
    width = min(n_g, n_p)
    miss = False
    wrong = False
    for i in range(width):
        gold_role = gold_roles[i]
        top = _topk_roles(glyphs[i], 5)
        if gold_role not in top:
            miss = True
            break
        if top and top[0] != gold_role:
            wrong = True
    if miss:
        return CellAttribution("CLS_MISS", gold_ply, raw, legal, n_g, n_p)
    if wrong:
        return CellAttribution("CLS_WRONG", gold_ply, raw, legal, n_g, n_p)
    decoded = decoder.decode_roles(tuple(str(g.get("role") or g.get("char")) for g in glyphs[:width]))
    if _castle_fold(decoded) != _castle_fold(gold_ply):
        return CellAttribution("DECODER", gold_ply, raw, legal, n_g, n_p, decoded)
    if _castle_fold(legal) != _castle_fold(gold_ply):
        return CellAttribution("GRAMMAR", gold_ply, raw, legal, n_g, n_p)
    return CellAttribution("OK", gold_ply, raw, legal, n_g, n_p)


def oracle_table(
    gold: GoldSheet,
    details: Sequence[Mapping[str, Any]],
    hypotheses: Sequence[CellHypothesis],
    decoder: CellDecoder,
) -> dict[str, Any]:
    n = min(len(gold.plies), len(details), len(hypotheses), len(gold.chars) or len(gold.plies))
    cats: list[CellAttribution] = []
    or1 = or3 = or5 = or_seg = or_upper = 0
    seg_ok = 0
    for i in range(n):
        chars = gold.chars[i] if i < len(gold.chars) else ()
        attr = attribute_cell(
            gold_ply=gold.plies[i],
            gold_chars=chars,
            detail=details[i],
            hypothesis=hypotheses[i],
            decoder=decoder,
        )
        cats.append(attr)
        gold_ply = gold.plies[i]
        cands = assemble_candidates(list(details[i].get("glyphs") or ()), decoder, k=3)
        folded = [_castle_fold(item) for item in cands]
        target = _castle_fold(gold_ply)
        if folded and folded[0] == target:
            or1 += 1
        if target in folded[:3]:
            or3 += 1
        wide = assemble_candidates(list(details[i].get("glyphs") or ()), decoder, k=5)
        wide_f = [_castle_fold(item) for item in wide]
        if target in wide_f[:5]:
            or5 += 1
        n_g = len(gold_roles_for_cell(chars))
        n_p = len(details[i].get("glyphs") or ())
        good_seg = n_g == n_p and n_g > 0
        if good_seg:
            seg_ok += 1
            if target in wide_f[:5]:
                or_seg += 1
        if target in wide_f or target == _castle_fold(str(details[i].get("raw") or "")):
            or_upper += 1
        elif attr.category in {"CLS_WRONG", "DECODER", "GRAMMAR"}:
            or_upper += 1
    counts = Counter(item.category for item in cats)
    denom = max(n, 1)
    return {
        "n": n,
        "categories": {key: int(counts.get(key, 0)) for key in CATEGORIES},
        "category_share": {key: counts.get(key, 0) / denom for key in CATEGORIES},
        "oracle1_cell": or1 / denom,
        "oracle3_cell": or3 / denom,
        "oracle5_cell": or5 / denom,
        "oracle_after_seg": (or_seg / seg_ok) if seg_ok else 0.0,
        "oracle_after_seg_n": seg_ok,
        "oracle_upper": or_upper / denom,
        "cells": [
            {
                "category": item.category,
                "gold": item.gold_ply,
                "raw": item.raw,
                "legal": item.legal,
                "n_gold_chars": item.n_gold_chars,
                "n_glyphs": item.n_glyphs,
                "notes": item.notes,
            }
            for item in cats
        ],
    }
