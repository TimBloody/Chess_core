"""Compare MSER glyph CNN (A) with a whole-cell CTC smoke test (B).

0006 and 0552 stay the development/evaluation sheets. B is not trained on them.
glyph_cnn.pt is read and hashed, never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from chess_core.app.experiments.ocr_mser import to_gray
from chess_core.infra.paths import project_root
from chess_core.ocr.blind_sheet import render_blind_sheet, shuffled_indices
from chess_core.ocr.candidates import CellCandidateList, scored_from_glyphs
from chess_core.ocr.cell_ctc import (
    INPUT_H,
    INPUT_W,
    MAX_LABEL_LEN,
    build_cell_ctc,
    candidates_from_log_probs,
    prepare_cell_image,
    roles_to_ctc_target,
)
from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.diag_stats import proportion
from chess_core.ocr.glyph_prep import PrepConfig, prepare_crop
from chess_core.ocr.gold import gold_dir, load_gold
from chess_core.ocr.move_norm import normalize_move_text, original_ink
from chess_core.ocr.roles import ROLE_IDS

EVAL_SHEETS = ("image_0006", "image_0552")
CHECKPOINT_SHA = "658971f0e6b45d3ded71ad688f112087137b4159c52e2ea9b127ab950d87efd3"
SMOKE_SEED = 0
SMOKE_N = 128
SMOKE_EPOCHS = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runs(sheet_id: str) -> Path:
    return project_root() / "output" / "ocr_runs" / f"{sheet_id}_cnn"


def _proto() -> Path:
    path = project_root() / "output" / "ocr_runs" / "p5_cell_proto"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _png(path: Path, image: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(path)
    encoded.tofile(str(path))


def _nearest(image: np.ndarray, scale: int) -> np.ndarray:
    import cv2

    if scale <= 1:
        return image
    height, width = image.shape[:2]
    return cv2.resize(image, (width * scale, height * scale), interpolation=cv2.INTER_NEAREST)


def _min_side(image: np.ndarray, side: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = max(1, math.ceil(side / max(min(height, width), 1)))
    return _nearest(image, scale)


def disputed_castle_index(sheet_id: str, payload: dict[str, object]) -> set[int]:
    """White move 8 on 0552 is ink 0-0 and is not rewritten to a legal castle."""

    if sheet_id != "image_0552":
        return set()
    plies = list(payload.get("plies") or [])
    ink = list(payload.get("raw_ru_prefix") or [])
    notes = str(payload.get("notes") or payload.get("note") or "")
    index = 14
    if index >= len(plies) or index >= len(ink):
        raise RuntimeError("0552 castle cell is missing from gold")
    if normalize_move_text(str(ink[index])) != "O-O" or normalize_move_text(str(plies[index])) != "O-O":
        raise RuntimeError("0552 ply 14 is no longer the disputed 0-0; do not guess a new gold")
    if "0-0" not in notes:
        raise RuntimeError("0552 note no longer describes the castling discrepancy")
    return {index}


def build_manifest() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sheet_id in EVAL_SHEETS:
        gold_path = gold_dir() / f"{sheet_id}.json"
        payload = json.loads(gold_path.read_text(encoding="utf-8"))
        gold = load_gold(sheet_id)
        if gold is None:
            raise FileNotFoundError(sheet_id)
        disputed = disputed_castle_index(sheet_id, payload)
        ink_rows = list(payload.get("raw_ru_prefix") or gold.plies)
        notation = str(payload.get("notation") or "en")
        if notation not in {"ru", "en"}:
            raise RuntimeError(f"{sheet_id} notation {notation}")
        cells = sorted((_runs(sheet_id) / "cells").glob("*.png"))
        if len(cells) < len(gold.plies):
            raise RuntimeError(f"{sheet_id}: cells {len(cells)} < gold {len(gold.plies)}")
        limit = max(len(cells), len(gold.plies))
        for index in range(limit):
            if index < len(cells):
                name = cells[index].name
                order_s, rest = name.split("_r", 1)
                row_s, col_s = rest.split("_c", 1)
                row = int(row_s)
                col = int(col_s.replace(".png", ""))
                order = int(order_s)
                crop = str(cells[index].relative_to(project_root()))
            else:
                name = ""
                row = col = order = None
                crop = None
            if index < len(gold.plies):
                status = "ambiguous" if index in disputed else "confirmed"
                gold_move = gold.plies[index]
                gold_ink = str(ink_rows[index]) if index < len(ink_rows) else gold_move
                n_chars = len(gold.chars[index]) if index < len(gold.chars) else None
            else:
                status = "missing"
                gold_move = None
                gold_ink = None
                n_chars = None
            rows.append(
                {
                    "sheet_id": sheet_id,
                    "writer_id": None,
                    "writer_id_reason": "автор почерка в gold не назван; имена партии не подставляем",
                    "row": row,
                    "col": col,
                    "order": order,
                    "bbox": None,
                    "bbox_reason": "в замороженном отчёте есть кроп клетки, нет бокса в пикселях таблицы",
                    "gold_move": gold_move,
                    "gold_ink": gold_ink,
                    "gold_normalized": None if gold_move is None else normalize_move_text(str(gold_ink)),
                    "gold_status": status,
                    "notation_mode": notation,
                    "n_gold_chars": n_chars,
                    "crop_path": crop,
                    "ply_index": index if status != "missing" else None,
                    "split_role": "development_evaluation",
                    "split_reason": "P2 и P5 уже смотрели 0006 и 0552; для переносимости нужен новый лист и автор",
                    "alignment": "assumed_stage12_occupied_order",
                }
            )
    return rows


def _details(sheet_id: str) -> tuple[list[dict[str, object]], str]:
    path = _runs(sheet_id) / "glyphs.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["cell_details"]), str(payload.get("notation_mode") or "ru")


def _live_glyphs(crop: Path) -> tuple[list[dict[str, object]], float]:
    """Top-10 roles per MSER glyph. The checkpoint is not written."""

    import torch

    from chess_core.app.experiments.ocr_glyphs import load_glyph_recognizer, weights_dir
    from chess_core.app.experiments.ocr_mser import segment_cell

    if not hasattr(_live_glyphs, "bundle"):
        _live_glyphs.bundle = load_glyph_recognizer(weights_dir())  # type: ignore[attr-defined]
    model, charset, device = _live_glyphs.bundle  # type: ignore[attr-defined]
    model = model.to(torch.device("cpu"))
    device = torch.device("cpu")
    started = time.perf_counter()
    split = segment_cell(crop)
    tiles = [glyph.mnist for glyph in split.glyphs]
    glyphs: list[dict[str, object]] = []
    if tiles:
        batch = np.stack(tiles).astype(np.float32) / 255.0
        tensor = torch.from_numpy(batch).unsqueeze(1).to(device)
        with torch.no_grad():
            probs = torch.softmax(model(tensor), dim=1)
            top = torch.topk(probs, k=min(10, len(charset)), dim=1)
        for row in range(len(tiles)):
            alts = [
                [charset[int(index)], float(score)]
                for index, score in zip(top.indices[row].tolist(), top.values[row].tolist())
            ]
            glyphs.append({"role": alts[0][0], "char": alts[0][0], "score": alts[0][1], "alts": alts})
    elapsed = time.perf_counter() - started
    return glyphs, elapsed


def score_branch_a(manifest: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    by_sheet: dict[str, tuple[list[dict[str, object]], str]] = {}
    scored: list[dict[str, object]] = []
    elapsed = 0.0
    counted = 0
    for row in manifest:
        if row["gold_status"] == "missing" or row["crop_path"] is None:
            continue
        sheet_id = str(row["sheet_id"])
        if sheet_id not in by_sheet:
            by_sheet[sheet_id] = _details(sheet_id)
        details, notation = by_sheet[sheet_id]
        ply = row["ply_index"]
        if not isinstance(ply, int) or ply >= len(details):
            raise RuntimeError(f"no stored read for {sheet_id} ply {ply}")
        detail = details[ply]
        live, seconds = _live_glyphs(project_root() / str(row["crop_path"]))
        elapsed += seconds
        counted += 1
        glyphs = live
        n_glyphs = len(live)
        decoder = CellDecoder(notation)
        candidates = scored_from_glyphs(glyphs, decoder, k=10)
        packet = CellCandidateList(
            sheet_id=sheet_id,
            ply_index=ply,
            source_cell=str(detail.get("file") or ""),
            notation_mode=str(row["notation_mode"]),
            candidates=candidates,
            uncertainty=tuple(
                flag
                for flag, on in (
                    ("ambiguous_gold", row["gold_status"] == "ambiguous"),
                    ("seg_mismatch", n_glyphs != row.get("n_gold_chars")),
                )
                if on
            ),
        )
        top_raw = candidates[0].raw if candidates else str(detail.get("raw") or "")
        scored.append(
            {
                "manifest": row,
                "n_glyphs": n_glyphs,
                "raw_top1": top_raw,
                "legal_flag": bool((detail.get("hypothesis") or {}).get("legal")),
                "candidates": packet.to_dict(),
            }
        )
    timing = {"device": "cpu", "seconds_per_cell": elapsed / max(counted, 1), "n": counted, "topk_per_glyph": 10}
    return scored, timing


def _confirmed(scored: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in scored if row["manifest"]["gold_status"] == "confirmed"]


def _recall(rows: list[dict[str, object]], k: int, *, which: str) -> dict[str, object]:
    hits = 0
    for row in rows:
        gold = str(row["manifest"]["gold_normalized"])
        cands = row[which]["candidates"][:k]
        hits += int(any(item["normalized"] == gold for item in cands))
    return proportion(hits, len(rows))


def _group_metrics(rows: list[dict[str, object]], which: str) -> dict[str, object]:
    if not rows:
        return {"n": 0, "reason": "нет подтверждённых клеток"}
    absent = 0
    for row in rows:
        gold = str(row["manifest"]["gold_normalized"])
        norms = [item["normalized"] for item in row[which]["candidates"]]
        absent += int(gold not in norms)
    seg_ok = [row for row in rows if row.get("n_glyphs") == row["manifest"].get("n_gold_chars")]
    seg_bad = [row for row in rows if row.get("n_glyphs") != row["manifest"].get("n_gold_chars")]
    return {
        "n": len(rows),
        "exact_top1": _recall(rows, 1, which=which),
        "recall_at_3": _recall(rows, 3, which=which),
        "recall_at_5": _recall(rows, 5, which=which),
        "recall_at_10": _recall(rows, 10, which=which),
        "gold_absent": proportion(absent, len(rows)),
        "seg_match_n": len(seg_ok),
        "seg_mismatch_n": len(seg_bad),
        "exact_top1_seg_match": _recall(seg_ok, 1, which=which) if seg_ok else None,
        "exact_top1_seg_mismatch": _recall(seg_bad, 1, which=which) if seg_bad else None,
        "recall_at_5_seg_match": _recall(seg_ok, 5, which=which) if seg_ok else None,
        "recall_at_5_seg_mismatch": _recall(seg_bad, 5, which=which) if seg_bad else None,
    }


def _by_notation(rows: list[dict[str, object]], which: str) -> dict[str, object]:
    out = {}
    for mode in ("en", "ru"):
        subset = [row for row in rows if row["manifest"]["notation_mode"] == mode]
        out[mode] = _group_metrics(subset, which) if subset else {"n": 0, "reason": "нет клеток"}
    return out


def assert_no_sheet_leak(train_sheets: list[str]) -> None:
    overlap = sorted(set(train_sheets) & set(EVAL_SHEETS))
    if overlap:
        raise RuntimeError(f"train/eval sheet leak: {overlap}")


def smoke_train_cell_ctc(dest: Path) -> dict[str, object]:
    """Fit the cell head on synthetic EMNIST lines only. Real sheets are not labels."""

    import torch
    from torchvision.datasets import EMNIST

    from chess_core.app.experiments.ocr_glyphs import emnist_keep_indices, emnist_root, to_mnist_glyph

    assert_no_sheet_leak([])
    torch.manual_seed(SMOKE_SEED)
    rng = np.random.default_rng(SMOKE_SEED)
    dataset = EMNIST(root=str(emnist_root()), split="byclass", train=True, download=False)
    data = dataset.data.numpy() if hasattr(dataset.data, "numpy") else np.asarray(dataset.data)
    targets = dataset.targets.numpy() if hasattr(dataset.targets, "numpy") else np.asarray(dataset.targets)
    keep = emnist_keep_indices()
    pools: dict[str, list[int]] = {role: [] for role in ROLE_IDS}
    for index, target in enumerate(targets.tolist()):
        role = keep.get(int(target))
        if role is not None and len(pools[role]) < 30:
            pools[role].append(index)
    usable = [role for role, idxs in pools.items() if idxs]
    if len(usable) < 8:
        raise RuntimeError("EMNIST did not yield enough role pools for a smoke line")
    images = []
    labels = []
    for _ in range(SMOKE_N):
        length = int(rng.integers(2, 5))
        roles = [str(usable[int(rng.integers(0, len(usable)))]) for _ in range(length)]
        tiles = []
        for role in roles:
            src = int(pools[role][int(rng.integers(0, len(pools[role])))])
            tiles.append(to_mnist_glyph(np.asarray(data[src], dtype=np.uint8), invert=True))
        gap = 4
        width = sum(tile.shape[1] for tile in tiles) + gap * (len(tiles) + 1)
        canvas = np.full((28, width), 255, dtype=np.uint8)
        x = gap
        for tile in tiles:
            canvas[:, x : x + tile.shape[1]] = tile
            x += tile.shape[1] + gap
        images.append(prepare_cell_image(canvas))
        labels.append(roles_to_ctc_target(roles))
        if len(roles) > MAX_LABEL_LEN:
            raise RuntimeError("smoke label longer than the CTC width budget")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_cell_ctc(torch).to(device)
    criterion = torch.nn.CTCLoss(blank=0, zero_infinity=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    losses = []
    model.train()
    for _epoch in range(SMOKE_EPOCHS):
        order = rng.permutation(len(images))
        epoch_loss = 0.0
        seen = 0
        for start in range(0, len(images), 32):
            batch_i = order[start : start + 32].tolist()
            batch = np.stack([images[i] for i in batch_i]).astype(np.float32) / 255.0
            tensor = torch.from_numpy(batch).unsqueeze(1).to(device)
            targets = torch.tensor([step for i in batch_i for step in labels[i]], dtype=torch.long)
            target_lengths = torch.tensor([len(labels[i]) for i in batch_i], dtype=torch.long)
            logits = model(tensor)
            input_lengths = torch.full((len(batch_i),), logits.shape[0], dtype=torch.long)
            loss = criterion(logits.log_softmax(2), targets, input_lengths, target_lengths)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach()) * len(batch_i)
            seen += len(batch_i)
        losses.append(epoch_loss / max(seen, 1))
    dest.mkdir(parents=True, exist_ok=True)
    weights = dest / "cell_ctc.pt"
    torch.save(model.state_dict(), weights)
    meta = {
        "kind": "synthetic_emnist_lines",
        "real_sheets": [],
        "seed": SMOKE_SEED,
        "n": SMOKE_N,
        "epochs": SMOKE_EPOCHS,
        "loss_first": losses[0],
        "loss_last": losses[-1],
        "device": str(device),
        "sha256": sha256_file(weights),
    }
    (dest / "cell_ctc_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def score_branch_b(scored_a: list[dict[str, object]], weights: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    import torch

    from chess_core.ocr.cell_ctc import build_cell_ctc as build

    device = torch.device("cpu")
    model = build(torch)
    model.load_state_dict(torch.load(weights, map_location=device, weights_only=True))
    model.to(device)
    model.eval()
    decoder = CellDecoder("ru")
    out = []
    elapsed = 0.0
    counted = 0
    for row in scored_a:
        crop = project_root() / str(row["manifest"]["crop_path"])
        gray = to_gray(crop)
        image = prepare_cell_image(gray)
        batch = image.astype(np.float32) / 255.0
        tensor = torch.from_numpy(batch).unsqueeze(0).unsqueeze(0)
        started = time.perf_counter()
        with torch.no_grad():
            logits = model(tensor)
        elapsed += time.perf_counter() - started
        counted += 1
        log_probs = logits[:, 0, :].log_softmax(-1)
        candidates = candidates_from_log_probs(log_probs, decoder, k=10)
        packet = CellCandidateList(
            sheet_id=str(row["manifest"]["sheet_id"]),
            ply_index=row["manifest"]["ply_index"] if isinstance(row["manifest"]["ply_index"], int) else None,
            source_cell=str(row["manifest"]["crop_path"]),
            notation_mode=str(row["manifest"]["notation_mode"]),
            candidates=candidates,
            uncertainty=("synthetic_weights",),
        )
        merged = dict(row)
        merged["b"] = packet.to_dict()
        out.append(merged)
    timing = {"device": "cpu", "seconds_per_cell": elapsed / max(counted, 1), "n": counted}
    return out, timing


def _pair_table(rows: list[dict[str, object]]) -> dict[str, object]:
    confirmed = [row for row in rows if row["manifest"]["gold_status"] == "confirmed" and "b" in row]
    both_wrong_but_topk = []
    a_only = []
    b_only = []
    neither = []
    union_hits = 0
    for row in confirmed:
        gold = str(row["manifest"]["gold_normalized"])
        a_norms = [item["normalized"] for item in row["candidates"]["candidates"]]
        b_norms = [item["normalized"] for item in row["b"]["candidates"]]
        a_top = bool(a_norms) and a_norms[0] == gold
        b_top = bool(b_norms) and b_norms[0] == gold
        a_has = gold in a_norms
        b_has = gold in b_norms
        item = {
            "sheet_id": row["manifest"]["sheet_id"],
            "ply_index": row["manifest"]["ply_index"],
            "crop_path": row["manifest"]["crop_path"],
            "gold": row["manifest"]["gold_ink"],
            "a_top": a_norms[0] if a_norms else None,
            "b_top": b_norms[0] if b_norms else None,
        }
        if a_top and not b_top:
            a_only.append(item)
        elif b_top and not a_top:
            b_only.append(item)
        elif not a_top and not b_top and (a_has or b_has):
            both_wrong_but_topk.append(item)
        elif not a_has and not b_has:
            neither.append(item)
        union_hits += int(a_has or b_has)
    return {
        "a_right_b_wrong": a_only,
        "b_right_a_wrong": b_only,
        "both_wrong_gold_in_some_topk": both_wrong_but_topk,
        "gold_in_neither": neither[:12],
        "union_recall_at_10": proportion(union_hits, len(confirmed)),
        "note": "B — перенос синтетических весов. Эта таблица не выбирает архитектуру.",
    }


def _examples(rows: list[dict[str, object]], limit: int = 10) -> list[dict[str, object]]:
    misses = []
    for row in _confirmed(rows):
        gold = str(row["manifest"]["gold_normalized"])
        cands = row["candidates"]["candidates"]
        top = cands[0]["normalized"] if cands else None
        if top == gold:
            continue
        misses.append(
            {
                "sheet_id": row["manifest"]["sheet_id"],
                "ply_index": row["manifest"]["ply_index"],
                "crop_path": row["manifest"]["crop_path"],
                "gold_ink": row["manifest"]["gold_ink"],
                "gold_normalized": gold,
                "a_raw_top1": row["raw_top1"],
                "a_topk": [item["raw"] for item in cands[:5]],
                "n_glyphs": row["n_glyphs"],
                "n_gold_chars": row["manifest"]["n_gold_chars"],
            }
        )
        if len(misses) >= limit:
            break
    return misses


def _emit_pack(manifest: list[dict[str, object]]) -> dict[str, str]:
    dest = _proto() / "label_pack"
    cells = [row for row in manifest if row["gold_status"] != "missing" and row["crop_path"]]
    order = shuffled_indices(len(cells), 701)
    images = []
    ids = []
    key_cells = []
    for position, source in enumerate(order):
        row = cells[source]
        gray = to_gray(project_root() / str(row["crop_path"]))
        images.append(_min_side(gray, 180))
        ids.append(f"c{position + 1:03d}")
        key_cells.append(
            {
                "id": ids[-1],
                "crop_path": row["crop_path"],
                "sheet_id": row["sheet_id"],
                "row": row["row"],
                "col": row["col"],
            }
        )
    canvas, captions = render_blind_sheet(images, ids, cols=2)
    if captions != ids:
        raise RuntimeError("cell sheet leaked a caption")
    _png(dest / "cells_blind.png", canvas)
    glyph_payload = json.loads((gold_dir() / "glyphs_real.json").read_text(encoding="utf-8"))
    glyph_rows = list(glyph_payload["glyphs"])
    g_order = shuffled_indices(len(glyph_rows), 702)
    g_images = []
    g_ids = []
    key_glyphs = []
    for position, source in enumerate(g_order):
        item = glyph_rows[source]
        raw = to_gray(gold_dir() / str(item["crop"]).split("data/gold/", 1)[-1])
        tile = prepare_crop(raw, PrepConfig())
        raw_v = _min_side(raw, 96)
        tile_v = _nearest(tile, 4)
        height = max(raw_v.shape[0], tile_v.shape[0])
        paired = np.full((height, raw_v.shape[1] + 8 + tile_v.shape[1]), 255, dtype=np.uint8)
        paired[: raw_v.shape[0], : raw_v.shape[1]] = raw_v
        paired[: tile_v.shape[0], raw_v.shape[1] + 8 :] = tile_v
        g_images.append(paired)
        g_ids.append(f"g{position + 1:03d}")
        key_glyphs.append({"id": g_ids[-1], "crop_path": item["crop"]})
    g_canvas, g_captions = render_blind_sheet(g_images, g_ids, cols=2)
    if g_captions != g_ids:
        raise RuntimeError("glyph sheet leaked a caption")
    _png(dest / "glyphs_blind.png", g_canvas)
    template = {
        "cells": [
            {
                "id": item["id"],
                "move_as_written": "",
                "status": "",
                "move_clear": None,
            }
            for item in key_cells
        ],
        "glyphs": [
            {
                "id": item["id"],
                "shape": "",
                "role_clear": None,
                "role": "",
            }
            for item in key_glyphs
        ],
    }
    (dest / "labels_template.json").write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "key.json").write_text(
        json.dumps({"cells": key_cells, "glyphs": key_glyphs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (dest / "INSTRUCTIONS.md").write_text(_instructions(), encoding="utf-8")
    return {
        "cells": str((dest / "cells_blind.png").relative_to(project_root())),
        "glyphs": str((dest / "glyphs_blind.png").relative_to(project_root())),
        "template": str((dest / "labels_template.json").relative_to(project_root())),
        "instructions": str((dest / "INSTRUCTIONS.md").relative_to(project_root())),
    }


def _instructions() -> str:
    return """# Разметка клеток и знаков

Листы анонимные. На картинке только id. Не открывайте key.json: там пути к файлам.

Знак (g###), левая картинка — кроп с фото, правая — тот же тензор 28×28, ближайшее увеличение в 4 раза, пиксели не сглажены.

Поле shape, одно значение:
- whole — один целый знак, форма читается
- fragment — обрывок
- glued — два знака в одном кропе
- grid — линия сетки или мусор
- unreadable — форма не разбирается

Роль (N, слон, пешечная буква) заполняйте только если она очевидна. K/К, C/С, b/B по одному 28×28 часто неразличимы: оставьте role пустым и role_clear=false. Не угадывайте шахматную роль.

Клетка (c###):
- move_as_written — как написано, русские буквы можно оставить
- status: readable, ambiguous или crossed_out
- move_clear: true, только если ход ясен по клетке целиком

Рокировку пишите как на бумаге. Если не отличить 0-0 от 0-0-0, ставьте ambiguous, не исправляйте на «легальный» ход.

Этого пакета мало для обучения. Следующему эксперименту нужно не меньше 300 подтверждённых клеток, не меньше 5 листов и 3 авторов, среди них русский бланк, и один автор целиком отложен в тест. Листы 0006 и 0552 уже использовались при настройке и остаются development/evaluation.
"""


def _write_report(payload: dict[str, object]) -> None:
    dest = _proto()
    (dest / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    a = payload["branch_a_confirmed"]
    b = payload.get("branch_b_confirmed") or {}
    lines = [
        "# Клетка целиком против MSER",
        "",
        str(payload["verdict"]),
        "",
        "P5 не закрыт. P3 и P4 не делались. glyph_cnn.pt не перезаписывался.",
        "",
        "## Gold",
        "",
        f"Подтверждённых клеток в точной оценке: {payload['n_confirmed']}.",
        f"Исключено как спорные: {payload['n_ambiguous']} (0552, белые, 8-й ход, чернила 0-0).",
        "Оба листа — development/evaluation: пороги прошлых шагов уже на них смотрели.",
        "writer_id нет: в gold не назван автор почерка.",
        "Порядок клеток — порядок занятых клеток stage12. Это соглашение пайплайна, не новая ручная сверка.",
        "",
        "## A, замороженный glyph CNN",
        "",
        f"exact top-1 {_fmt(a, 'exact_top1')}",
        f"recall@3 {_fmt(a, 'recall_at_3')}",
        f"recall@5 {_fmt(a, 'recall_at_5')}",
        f"recall@10 {_fmt(a, 'recall_at_10')}",
        f"gold нет среди кандидатов {_fmt(a, 'gold_absent')}",
        f"MSER-число совпало с числом знаков: {a.get('seg_match_n')} из {a.get('n')}.",
        f"exact top-1 при совпавшей нарезке {_fmt(a, 'exact_top1_seg_match')}",
        f"exact top-1 при несовпавшей нарезке {_fmt(a, 'exact_top1_seg_mismatch')}",
        f"доля клеток с флагом legal (это не точность): {_fmt(payload, 'legal_flag_rate_not_accuracy')}",
        "",
        "## B, синтетический CTC",
        "",
        "Обучение только на склеенных строках EMNIST. Реальные клетки в обучение не входили.",
        f"exact top-1 {_fmt(b, 'exact_top1') if b else 'null — смоук не запускался'}",
        f"recall@5 {_fmt(b, 'recall_at_5') if b else 'null'}",
        "",
        "Эти числа B не выбирают архитектуру: модель не видела подтверждённых клеток.",
        "",
        "## Ошибки A",
        "",
    ]
    for item in payload.get("examples_a_miss") or []:
        if isinstance(item, dict):
            lines.append(
                f"- {item['sheet_id']} ply {item['ply_index']} gold {item['gold_ink']} "
                f"A {item['a_raw_top1']} glyphs {item['n_glyphs']}/{item['n_gold_chars']} "
                f"`{item['crop_path']}`"
            )
    lines.extend(["", str(payload["next_step"]), ""])
    text = lines
    (dest / "REPORT.md").write_text("\n".join(text), encoding="utf-8")


def _fmt(block: dict[str, object], key: str) -> str:
    item = block.get(key)
    if not isinstance(item, dict) or "p" not in item:
        return "null"
    lo = max(0.0, float(item["ci95_lo"]))
    hi = min(1.0, float(item["ci95_hi"]))
    return f"{item['hits']}/{item['n']} = {float(item['p']):.3f} (95% ДИ {lo:.3f}–{hi:.3f})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cell-vs-glyph diagnostic. No gold training.")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args(argv)
    weights = project_root() / "output" / "ocr_glyph_cnn" / "glyph_cnn.pt"
    before = sha256_file(weights)
    if before != CHECKPOINT_SHA:
        raise SystemExit(f"glyph_cnn.pt hash changed: {before}")
    stage12 = project_root() / "src" / "chess_core" / "app" / "experiments" / "ocr_stage12.py"
    stage12_sha = sha256_file(stage12)
    manifest = build_manifest()
    scored, timing_a = score_branch_a(manifest)
    confirmed = _confirmed(scored)
    pack = _emit_pack(manifest)
    smoke: dict[str, object] | None = None
    timing_b: dict[str, object] | None = None
    pairs: dict[str, object] | None = None
    branch_b: dict[str, object] | None = None
    if not args.skip_smoke:
        smoke = smoke_train_cell_ctc(_proto())
        assert_no_sheet_leak(list(smoke["real_sheets"]))  # type: ignore[arg-type]
    weights_b = _proto() / "cell_ctc.pt"
    if weights_b.is_file():
        if smoke is None:
            smoke = json.loads((_proto() / "cell_ctc_meta.json").read_text(encoding="utf-8"))
        scored, timing_b = score_branch_b(scored, weights_b)
        confirmed = _confirmed(scored)
        branch_b = _group_metrics(confirmed, "b")
        pairs = _pair_table(scored)
    import torch

    from chess_core.ocr.cell_ctc import build_cell_ctc as _build

    glyph_params = sum(int(p.numel()) for p in _live_glyphs.bundle[0].parameters())  # type: ignore[attr-defined]
    cell_params = sum(int(p.numel()) for p in _build(torch).parameters())
    after = sha256_file(weights)
    if after != before:
        raise SystemExit("glyph_cnn.pt was overwritten")
    if sha256_file(stage12) != stage12_sha:
        raise SystemExit("stage12 file changed during the run")
    n_ambiguous = sum(1 for row in manifest if row["gold_status"] == "ambiguous")
    payload: dict[str, object] = {
        "step": "cell_vs_mser",
        "p5_closed": False,
        "p3_started": False,
        "p4_started": False,
        "checkpoint_sha256": after,
        "stage12_sha256": stage12_sha,
        "split_role": "development_evaluation",
        "n_manifest": len(manifest),
        "n_confirmed": len(confirmed),
        "n_ambiguous": n_ambiguous,
        "branch_a_confirmed": _group_metrics(confirmed, "candidates"),
        "legal_flag_rate_not_accuracy": proportion(
            sum(int(bool(row.get("legal_flag"))) for row in confirmed),
            len(confirmed),
        ),
        "branch_a_by_notation": _by_notation(confirmed, "candidates"),
        "branch_b_confirmed": branch_b,
        "branch_b_training": smoke,
        "model_sizes": {
            "glyph_cnn_parameters": glyph_params,
            "glyph_cnn_bytes": weights.stat().st_size,
            "cell_ctc_parameters": cell_params,
            "cell_ctc_bytes": (_proto() / "cell_ctc.pt").stat().st_size if (_proto() / "cell_ctc.pt").is_file() else None,
        },
        "branch_a_cpu_seconds_per_cell": timing_a,
        "branch_b_cpu_seconds_per_cell": timing_b,
        "pairs": pairs,
        "examples_a_miss": _examples(scored, 10),
        "label_pack": pack,
        "verdict": (
            "Данных пока недостаточно. B обучена только на синтетических строках, "
            "подтверждённого сравнения на фото нет. Архитектурное решение отложено, B не победила."
            if smoke is not None
            else "Данных пока недостаточно: смоук B не запускался, решение отложено."
        ),
        "next_step": (
            "Нужна ручная разметка клеток из label_pack: ход как написан, ambiguous/crossed_out. "
            "Не меньше 300 клеток, 5 листов, 3 авторов, русский бланк, один автор в тесте. "
            "0552 ход 8 белых не подтверждать догадкой."
        ),
    }
    _write_report(payload)
    (_proto() / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(payload["verdict"], flush=True)
    print("confirmed", len(confirmed), "ambiguous", n_ambiguous, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
