"""Legal-SAN snap and neighbour-sheet ground truth."""

from __future__ import annotations

from chess_core.app.experiments.ocr_eval import load_sheet_truth, parse_cell_name
from chess_core.app.experiments.ocr_language import (
    constrain_cell_reads,
    levenshtein,
    pick_legal_san,
)
from chess_core.app.experiments.ocr_stage12 import ocr_project_root
from chess_core.app.game import LocalGameService
from chess_core.modes.chess import classic_chess


def test_levenshtein_and_cell_name() -> None:
    assert levenshtein("cO2", "c4") == 2
    assert parse_cell_name("0002_r02_c01.png") == (2, 2, 1)


def test_opening_c4_is_legal_snap() -> None:
    from chess_core.app.experiments.ocr_language import legal_catalog

    catalog = legal_catalog(LocalGameService(classic_chess()))
    picked = pick_legal_san("c4", catalog)
    assert picked is not None
    assert picked[0] == "c4"
    picked_noisy = pick_legal_san("cO2", catalog)
    if picked_noisy is not None:
        assert picked_noisy[0] in {row[0] for row in catalog}


def test_constrain_walks_opening() -> None:
    reads = constrain_cell_reads(("c4", "c6", "Nc3", "????", "xxxxx"))
    assert reads[0] == "c4"
    assert reads[1] == "c6"
    assert reads[2] == "Nc3"
    assert all(text for text in reads)
    assert reads[3] == "????"
    assert reads[4] == "xxxxx"


def test_image_0006_truth_exists_in_neighbour() -> None:
    root = ocr_project_root()
    if root is None:
        return
    truth = load_sheet_truth(root / "data" / "raw" / "image_0006.jpg")
    if truth is None:
        return
    assert truth.moves[:4] == ("c4", "c6", "Nc3", "g5")
    assert len(truth.moves) == 24
