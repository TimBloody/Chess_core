"""Per-glyph accuracy on real scoresheet crops. This is the P5 ruler."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

import numpy as np

from chess_core.ocr.roles import ROLE_IDS


def roc_auc(scores: Sequence[float], correct: Sequence[int]) -> float:
    """AUC of confidence as a predictor of correctness. 0.5 means useless."""

    y = np.asarray(correct, dtype=np.int64)
    s = np.asarray(scores, dtype=np.float64)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=np.float64)
    ranks[order] = np.arange(1, len(s) + 1, dtype=np.float64)
    # Average ranks for ties.
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and s[order[end]] == s[order[start]]:
            end += 1
        if end - start > 1:
            avg = float(ranks[order[start:end]].mean())
            ranks[order[start:end]] = avg
        start = end
    sum_pos = float(ranks[y == 1].sum())
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def evaluate_predictions(
    gold_roles: Sequence[str],
    top_roles: Sequence[Sequence[str]],
    confidences: Sequence[float],
) -> dict[str, object]:
    """top_roles[i][0] is top-1. Missing gold in the list counts as a top-5 miss."""

    if not (len(gold_roles) == len(top_roles) == len(confidences)):
        raise ValueError("gold, predictions and confidences must be aligned")
    n = len(gold_roles)
    if n == 0:
        raise ValueError("empty glyph set")
    top1_hit = 0
    top5_hit = 0
    per_role_hit: dict[str, list[int]] = defaultdict(list)
    matrix = [[0 for _ in ROLE_IDS] for _ in ROLE_IDS]
    index = {role_id: i for i, role_id in enumerate(ROLE_IDS)}
    correct_flags: list[int] = []
    confident_wrong = 0
    for gold, ranked, conf in zip(gold_roles, top_roles, confidences):
        pred = ranked[0] if ranked else ""
        hit1 = pred == gold
        hit5 = gold in ranked[:5]
        top1_hit += int(hit1)
        top5_hit += int(hit5)
        per_role_hit[gold].append(int(hit1))
        correct_flags.append(int(hit1))
        if (not hit1) and float(conf) > 0.9:
            confident_wrong += 1
        if gold in index and pred in index:
            matrix[index[gold]][index[pred]] += 1
    pairs: list[dict[str, object]] = []
    for gold_i, gold in enumerate(ROLE_IDS):
        for pred_i, pred in enumerate(ROLE_IDS):
            count = matrix[gold_i][pred_i]
            if gold_i != pred_i and count:
                pairs.append({"gold": gold, "pred": pred, "n": int(count)})
    pairs.sort(key=lambda row: (-int(row["n"]), str(row["gold"]), str(row["pred"])))
    per_role = {
        role_id: (sum(hits) / len(hits) if hits else None)
        for role_id, hits in ((role, per_role_hit.get(role, [])) for role in ROLE_IDS)
    }
    support = {role_id: len(per_role_hit.get(role_id, [])) for role_id in ROLE_IDS}
    return {
        "n": n,
        "per_glyph_top1": top1_hit / n,
        "per_glyph_top5": top5_hit / n,
        "top5_miss_share": 1.0 - top5_hit / n,
        "per_role_top1": per_role,
        "per_role_support": support,
        "confusion": matrix,
        "role_ids": list(ROLE_IDS),
        "top_confusions": pairs[:10],
        "confident_wrong_gt_0.9": confident_wrong,
        "conf_correct_auc": roc_auc(confidences, correct_flags),
        "conf_mean": float(np.mean(np.asarray(confidences, dtype=np.float64))),
        "conf_median": float(np.median(np.asarray(confidences, dtype=np.float64))),
    }


def ink_brightness(tile: np.ndarray, *, dark_below: int = 175) -> tuple[float, float]:
    gray = np.asarray(tile)
    if gray.ndim == 3:
        gray = gray[..., 0]
    ink = gray < dark_below
    if not np.any(ink):
        return float(gray.mean()), 255.0
    return float(gray.mean()), float(gray[ink].mean())


def brightness_summary(tiles: Sequence[np.ndarray]) -> dict[str, float]:
    means = []
    inks = []
    for tile in tiles:
        mean, ink = ink_brightness(tile)
        means.append(mean)
        inks.append(ink)
    arr_m = np.asarray(means, dtype=np.float64)
    arr_i = np.asarray(inks, dtype=np.float64)
    return {
        "n": float(len(tiles)),
        "tile_mean": float(arr_m.mean()) if len(tiles) else 0.0,
        "tile_median": float(np.median(arr_m)) if len(tiles) else 0.0,
        "ink_mean": float(arr_i.mean()) if len(tiles) else 0.0,
        "ink_median": float(np.median(arr_i)) if len(tiles) else 0.0,
    }


def histogram(values: Sequence[float], *, bins: int = 16, lo: float = 0.0, hi: float = 255.0) -> dict[str, list[float]]:
    counts, edges = np.histogram(np.asarray(values, dtype=np.float64), bins=bins, range=(lo, hi))
    return {"edges": [float(x) for x in edges], "counts": [int(x) for x in counts]}


