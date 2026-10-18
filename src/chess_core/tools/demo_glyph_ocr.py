"""Cut a real scoresheet and show deskew / split / MSER / CNN in a window.

Examples:

    python -m chess_core.tools.demo_glyph_ocr
    python -m chess_core.tools.demo_glyph_ocr --input image_0006.jpg
    python -m chess_core.tools.demo_glyph_ocr --input path/to/photo.jpg
    python -m chess_core.tools.demo_glyph_ocr --no-window
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from chess_core.app.experiments.ocr import (
    default_demo_input,
    default_output_dir,
    resolve_input,
    run_scoresheet_pipeline,
)
from chess_core.app.experiments.ocr_glyphs import weights_dir


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _print_run(run) -> None:
    print(f"input={run.source}")
    print(f"engine={run.engine}")
    print(
        f"grid={run.grid_rows}x{run.grid_cols} "
        f"occupied={run.occupied_cells} read={len(run.cell_reads)}"
    )
    for stage in run.stages:
        print(f"stage={stage.key} {stage.title}: {stage.path}")
        if stage.note:
            print(f"  note={stage.note}")
    dump = run.output_dir / "report.json"
    hyps = []
    if dump.is_file():
        import json

        hyps = json.loads(dump.read_text(encoding="utf-8")).get("hypotheses") or []
    for index, text in enumerate(run.cell_reads):
        hypo = hyps[index] if index < len(hyps) else {}
        legal = hypo.get("text", "")
        flag = hypo.get("reason", "")
        print(f"cell={index + 1:02d}  raw={text!r}  out={legal!r}  {flag}")
    if run.moves:
        print(f"legal={' '.join(run.moves)}")
    print(f"output={run.output_dir}")
    report_path = run.output_dir / "report.json"
    if report_path.is_file():
        print(f"report={report_path}")
    metrics_path = run.output_dir / "glyphs.json"
    if metrics_path.is_file():
        print(f"dump={metrics_path}")


def _show_window(run) -> int:
    from chess_core.ui.experiments.ocr_stages import ensure_qt_app, play_scoresheet_stages

    ensure_qt_app()
    play_scoresheet_stages(run)
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description=(
            "Этапы бланка по очереди, каждое окно на весь экран. "
            "Закройте текущее — откроется следующее: выравнивание, шапка/таблица, MSER, CNN. "
            "Без --input — image_0006.jpg из data/raw соседнего OCR."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Фото бланка. Если не задан — базовый скан соседнего проекта.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help=f"Папка с glyph_cnn.pt и labels.json. По умолчанию {weights_dir()}",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Только консоль и файлы, без окна этапов.",
    )
    parser.add_argument(
        "--notation",
        choices=("ru", "en"),
        default="ru",
        help="KN перед полем: ru=конь, en=король. Гипотеза авто-детекта пишется в dump, не применяется.",
    )
    parser.add_argument(
        "--gate",
        choices=("off", "soft", "hard"),
        default="soft",
        help="content-gate: off=как P1, soft=default, hard=не звать CNN на отвергнутых кропах.",
    )
    args = parser.parse_args(argv)

    source = resolve_input(args.input) if args.input is not None else default_demo_input()
    output = args.output_dir or default_output_dir(source.stem + "_cnn")
    run = run_scoresheet_pipeline(
        source,
        output,
        weights=args.weights,
        notation_mode=args.notation,
        gate_mode=args.gate,
    )
    _print_run(run)
    if args.no_window:
        return 0
    return _show_window(run)


if __name__ == "__main__":
    raise SystemExit(main())
