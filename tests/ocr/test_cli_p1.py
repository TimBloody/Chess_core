"""P0 CLI still works without new flags; notation default is ru."""

from __future__ import annotations

from chess_core.app.experiments.ocr import run_scoresheet_pipeline
from chess_core.tools import demo_glyph_ocr, train_glyph_cnn


def test_demo_help_does_not_require_notation() -> None:
    raised = None
    try:
        demo_glyph_ocr.main(["--help"])
    except SystemExit as exc:
        raised = exc
    assert raised is not None
    assert raised.code == 0


def test_train_latin_only_flag_still_exists() -> None:
    raised = None
    try:
        train_glyph_cnn.main(["--help"])
    except SystemExit as exc:
        raised = exc
    assert raised is not None
    assert raised.code == 0


def test_pipeline_notation_default_is_ru() -> None:
    import inspect

    spec = inspect.signature(run_scoresheet_pipeline)
    assert spec.parameters["notation_mode"].default == "ru"
