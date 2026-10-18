"""Run the scoresheet OCR experiment from the terminal.

Examples:

    python -m chess_core.tools.ocr_scoresheet
    python -m chess_core.tools.ocr_scoresheet --input image_0006.jpg
    python -m chess_core.tools.ocr_scoresheet --input path/to/photo.jpg
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from chess_core.app.experiments.ocr import (
    default_inputs,
    default_output_dir,
    ocr_project_root,
    resolve_input,
    run_scoresheet_pipeline,
    samples_dir,
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        description="Реальная сетка бланка (stage12 соседнего OCR). Без --input — случайный data/raw."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Фото бланка. Если не задан — случайный data/raw/image_*.jpg соседнего OCR.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--list", action="store_true", help="Показать доступные бланки и выйти.")
    args = parser.parse_args(argv)

    if args.list:
        photos = default_inputs()
        print(f"ocr_project={ocr_project_root()}")
        print(f"synthetic={samples_dir()}")
        print(f"count={len(photos)}")
        for path in photos[:20]:
            print(path)
        if len(photos) > 20:
            print(f"... and {len(photos) - 20} more")
        return 0

    source = resolve_input(args.input)
    output = args.output_dir or default_output_dir(source.stem)
    run = run_scoresheet_pipeline(source, output)
    print(f"input={run.source}")
    print(f"engine={run.engine}")
    if run.moves:
        print(f"moves={' '.join(run.moves)}")
    print(
        f"grid={run.grid_rows}x{run.grid_cols} "
        f"lines=H{run.h_lines}/V{run.v_lines} occupied={run.occupied_cells}"
    )
    print(f"output={run.output_dir}")
    for stage in run.stages:
        print(f"stage={stage.key} {stage.title}: {stage.path}")
    print(f"glyphs={run.pgn_path}")
    for note in run.notes:
        if note:
            print(f"note={note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
