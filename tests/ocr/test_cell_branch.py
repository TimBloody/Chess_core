"""Cell-vs-glyph protocol: gold alignment, normalization, CTC width, no sheet leak."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import torch

from chess_core.infra.paths import project_root
from chess_core.ocr.candidates import MoveCandidate, attach_legality, ensure_sorted
from chess_core.ocr.cell_ctc import (
    MAX_LABEL_LEN,
    build_cell_ctc,
    candidates_from_log_probs,
    greedy_roles,
    time_steps,
)
from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.gold import list_gold_ids
from chess_core.ocr.move_norm import normalize_move_text, original_ink
from chess_core.ocr.roles import ROLE_IDS
from chess_core.tools.audit_cell_branch import (
    CHECKPOINT_SHA,
    EVAL_SHEETS,
    assert_no_sheet_leak,
    build_manifest,
    disputed_castle_index,
)


def test_gold_lists_are_sheets_not_glyph_dumps() -> None:
    assert list_gold_ids() == EVAL_SHEETS


def test_castle_cell_is_ambiguous_and_not_rewritten() -> None:
    import json

    from chess_core.ocr.gold import gold_dir

    payload = json.loads((gold_dir() / "image_0552.json").read_text(encoding="utf-8"))
    assert disputed_castle_index("image_0552", payload) == {14}
    assert payload["plies"][14] == "O-O"
    assert payload["raw_ru_prefix"][14] == "0-0"
    rows = build_manifest()
    disputed = [row for row in rows if row["gold_status"] == "ambiguous"]
    assert len(disputed) == 1
    assert disputed[0]["sheet_id"] == "image_0552"
    assert disputed[0]["ply_index"] == 14
    confirmed = [row for row in rows if row["gold_status"] == "confirmed"]
    assert all(row["writer_id"] is None for row in rows)
    assert {row["sheet_id"] for row in confirmed} == set(EVAL_SHEETS)
    first = next(row for row in rows if row["sheet_id"] == "image_0006" and row["ply_index"] == 0)
    assert first["gold_move"] == "c4"
    assert first["crop_path"].endswith("0000_r01_c01.png")
    assert Path(first["crop_path"]).is_file() or (project_root() / first["crop_path"]).is_file()


def test_russian_ink_is_kept_and_folded() -> None:
    knight_c = "\u041a\u04413"
    assert original_ink(knight_c) == knight_c
    assert normalize_move_text(knight_c) == "Nc3"
    assert normalize_move_text("\u0421e7") == "Be7"
    assert normalize_move_text("\u0424d6") == "Qd6"
    assert normalize_move_text("\u041bb1") == "Rb1"
    assert normalize_move_text("\u041a\u0440e1") == "Ke1"
    assert normalize_move_text("0-0") == "O-O"
    assert normalize_move_text("0-0-0") == "O-O-O"
    assert normalize_move_text("Nc3") == "Nc3"


def test_train_sheets_cannot_include_the_eval_pair() -> None:
    assert_no_sheet_leak([])
    with pytest.raises(RuntimeError):
        assert_no_sheet_leak(["image_0006"])


def test_ctc_time_steps_cover_the_longest_move() -> None:
    assert time_steps() >= MAX_LABEL_LEN
    model = build_cell_ctc(torch)
    images = torch.zeros(2, 1, 32, 128)
    logits = model(images)
    assert logits.shape[0] == time_steps()
    assert logits.shape[0] >= MAX_LABEL_LEN
    assert logits.shape[2] == len(ROLE_IDS) + 1


def test_greedy_ctc_reads_a_peaked_path() -> None:
    classes = len(ROLE_IDS) + 1
    log_probs = torch.full((8, classes), -8.0)
    file_c = ROLE_IDS.index("f_c") + 1
    rank_4 = ROLE_IDS.index("r_4") + 1
    log_probs[0, 0] = 0.0
    log_probs[1, file_c] = 0.0
    log_probs[2, 0] = 0.0
    log_probs[3, rank_4] = 0.0
    log_probs[4:, 0] = 0.0
    assert greedy_roles(log_probs) == ("f_c", "r_4")
    ranked = candidates_from_log_probs(log_probs, CellDecoder("ru"), k=3)
    assert ranked[0].normalized == "c4"
    assert [item.log_score for item in ranked] == sorted((item.log_score for item in ranked), reverse=True)


def test_legality_does_not_drop_or_reorder() -> None:
    rows = (
        MoveCandidate("Nc3", "Nc3", -0.2, ("KN", "f_c", "r_3")),
        MoveCandidate("c4", "c4", -1.5, ("f_c", "r_4")),
    )
    flagged = attach_legality(rows, (False, True))
    assert [item.raw for item in flagged] == ["Nc3", "c4"]
    assert [item.legal for item in flagged] == [False, True]
    ensure_sorted(rows)
    with pytest.raises(ValueError):
        ensure_sorted(tuple(reversed(rows)))


def test_checkpoint_and_stage12_files_are_the_frozen_ones() -> None:
    weights = project_root() / "output" / "ocr_glyph_cnn" / "glyph_cnn.pt"
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    assert digest == CHECKPOINT_SHA
    stage12 = project_root() / "src" / "chess_core" / "app" / "experiments" / "ocr_stage12.py"
    assert "def run_stage12_preprocess" in stage12.read_text(encoding="utf-8")
    assert np is not None
