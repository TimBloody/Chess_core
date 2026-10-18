"""Scoresheet OCR experiment: stage12 grid and MNIST-sized glyphs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import random

from chess_core.app.experiments.ocr_render import (
    ensure_gui,
    render_scoresheet,
    scoresheet_grid,
)
from chess_core.app.experiments.ocr_stage12 import (
    ocr_project_root,
    raw_scoresheet_images,
    run_stage12_preprocess,
)
from chess_core.infra.paths import project_root

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass(frozen=True, slots=True)
class OcrSample:
    sample_id: str
    image: Path
    moves: tuple[str, ...]
    white: str
    black: str
    event: str
    result: str
    rotate_deg: float = 0.0


@dataclass(frozen=True, slots=True)
class OcrStage:
    key: str
    title: str
    path: Path
    note: str = ""


@dataclass(frozen=True, slots=True)
class OcrRun:
    source: Path
    output_dir: Path
    stages: tuple[OcrStage, ...]
    moves: tuple[str, ...]
    pgn: str
    pgn_path: Path
    engine: str
    notes: tuple[str, ...] = field(default_factory=tuple)
    grid_rows: int = 0
    grid_cols: int = 0
    occupied_cells: int = 0
    h_lines: int = 0
    v_lines: int = 0
    cell_reads: tuple[str, ...] = ()


def samples_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "experiments" / "ocr"


def default_output_dir(stem: str) -> Path:
    return project_root() / "output" / "ocr_runs" / stem


_FIXTURES: tuple[dict[str, object], ...] = (
    {
        "id": "italian",
        "file": "italian.png",
        "white": "Алиса",
        "black": "Борис",
        "event": "Фикстура OCR / Italian",
        "result": "*",
        "rotate_deg": 0.0,
        "moves": ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"),
    },
    {
        "id": "scholar",
        "file": "scholar.png",
        "white": "Вера",
        "black": "Глеб",
        "event": "Фикстура OCR / Scholar",
        "result": "1-0",
        "rotate_deg": 0.0,
        "moves": ("e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"),
    },
    {
        "id": "rotated",
        "file": "rotated.png",
        "white": "Алиса",
        "black": "Борис",
        "event": "Фикстура OCR / deskew",
        "result": "*",
        "rotate_deg": 3.2,
        "moves": ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"),
    },
)


def _sidecar_path(image: Path) -> Path:
    return image.with_suffix(".json")


def write_samples(directory: Path | None = None) -> list[Path]:
    """Create optional synthetic blanks. They are not the default input."""

    ensure_gui()
    root = directory or samples_dir()
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    catalog: list[dict[str, object]] = []
    for spec in _FIXTURES:
        image_path = root / str(spec["file"])
        moves = tuple(spec["moves"])  # type: ignore[arg-type]
        image = render_scoresheet(
            moves,
            white=str(spec["white"]),
            black=str(spec["black"]),
            event=str(spec["event"]),
            rotate_deg=float(spec["rotate_deg"]),
        )
        image.save(str(image_path), "PNG")
        payload = {
            "id": spec["id"],
            "moves": list(moves),
            "white": spec["white"],
            "black": spec["black"],
            "event": spec["event"],
            "result": spec["result"],
            "rotate_deg": spec["rotate_deg"],
            "grid": scoresheet_grid(),
        }
        _sidecar_path(image_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        catalog.append({"id": spec["id"], "file": spec["file"]})
        written.append(image_path)
    (root / "manifest.json").write_text(
        json.dumps({"samples": catalog, "grid": scoresheet_grid()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return written


def list_sample_images(directory: Path | None = None) -> list[Path]:
    root = directory or samples_dir()
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES
    )


def load_sample(image: Path) -> OcrSample | None:
    sidecar = _sidecar_path(image)
    if not sidecar.is_file():
        return None
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return OcrSample(
        sample_id=str(data.get("id") or image.stem),
        image=image,
        moves=tuple(str(item) for item in data.get("moves") or ()),
        white=str(data.get("white") or "?"),
        black=str(data.get("black") or "?"),
        event=str(data.get("event") or "OCR fixture"),
        result=str(data.get("result") or "*"),
        rotate_deg=float(data.get("rotate_deg") or 0.0),
    )


def default_inputs() -> list[Path]:
    """Real photographed blanks from the neighbour OCR project, if present."""

    photos = raw_scoresheet_images()
    if photos:
        return photos
    return list_sample_images()


def pick_random_input(
    directory: Path | None = None,
    *,
    rng: random.Random | None = None,
) -> Path:
    images = list_sample_images(directory) if directory is not None else default_inputs()
    if not images:
        raise FileNotFoundError("нет бланков: ни data/raw соседнего OCR, ни bundled PNG")
    return (rng or random.Random()).choice(images)


_DEFAULT_DEMO_NAME = "image_0006.jpg"


def default_demo_input() -> Path:
    """Stable neighbour-OCR scan, or the first raw photo if that name is missing."""

    try:
        return resolve_input(_DEFAULT_DEMO_NAME)
    except FileNotFoundError:
        photos = default_inputs()
        if not photos:
            raise FileNotFoundError("нет бланков: ни data/raw соседнего OCR, ни bundled PNG")
        return photos[0]


def resolve_input(raw: str | Path | None, *, rng: random.Random | None = None) -> Path:
    if raw is None:
        return pick_random_input(rng=rng)
    path = Path(raw)
    if path.is_file():
        return path.resolve()
    nested = samples_dir() / path
    if nested.is_file():
        return nested.resolve()
    by_name = samples_dir() / path.name
    if by_name.is_file():
        return by_name.resolve()
    ocr_root = ocr_project_root()
    if ocr_root is not None:
        for candidate in (
            ocr_root / "data" / "raw" / path.name,
            ocr_root / "data" / "examples" / "samples" / path.name,
            ocr_root / path,
        ):
            if candidate.is_file():
                return candidate.resolve()
    raise FileNotFoundError(raw)


_STAGE_SPECS: dict[str, tuple[str, str]] = {
    "00_original.jpg": ("1. Вход", "исходное фото"),
    "01_deskewed.jpg": ("2. Выравнивание", "если лист косой — ломается всё дальше"),
    "02_split_overlay.jpg": ("3. Шапка / таблица", "граница между заголовком и ходами"),
    "03_header.jpg": ("4. Шапка", "имена и событие; ходы здесь не читаем"),
    "04_game_table.jpg": ("5. Таблица ходов", "только сетка партии"),
    "05_grid_lines.jpg": ("6. Сетка", "линии должны совпасть с клетками бланка"),
    "06_grid_order.jpg": ("7. Порядок клеток", "ход за ходом: белые, чёрные"),
    "07_grid_preview.png": ("8. Превью клеток", "вырезанные ячейки таблицы до нарезки знаков"),
    "08_mser_glyphs.jpg": ("9. MSER", "рамки вокруг знаков; склейка — ошибка нарезки"),
    "09_mnist_glyphs.jpg": ("10. Символы 28×28", "вход CNN: тёмные чернила, белое поле"),
    "10_cnn_glyphs.png": ("11. CNN", "подпись под знаком; роли, не буквы"),
}


def _collect_stages(stage12, cnn_stage: OcrStage) -> list[OcrStage]:
    """Always emit every diagnostic card, even when a step did not write a file."""

    present = {path.name: path for path in stage12.stage_files}
    stages: list[OcrStage] = []
    for name, (title, note) in _STAGE_SPECS.items():
        if name == "10_cnn_glyphs.png":
            stages.append(cnn_stage)
            continue
        path = present.get(name, stage12.output_dir / name)
        if path.is_file():
            stages.append(OcrStage(name, title, path, note))
        else:
            stages.append(OcrStage(name, title, path, f"{note}  ·  этап не дал картинку"))
    return stages


def _cnn_stage(
    cell_paths: tuple[Path, ...],
    destination: Path,
    *,
    weights: Path | None = None,
    notation_mode: str = "ru",
    gate_mode: str = "soft",
) -> tuple[OcrStage, tuple[str, ...], list[dict], list[str]]:
    from chess_core.app.experiments.ocr_eval import parse_cell_name
    from chess_core.app.experiments.ocr_glyphs import (
        GARBAGE,
        load_glyph_recognizer,
        predict_mnist_tiles,
        save_labeled_montage,
    )
    from chess_core.app.experiments.ocr_mser import segment_cell, to_gray
    from chess_core.ocr.gate import load_content_gate
    from chess_core.ocr.gate.geometry import SheetGeometry
    from chess_core.ocr.gate.integrity import inspect_cell_glyphs

    cnn_path = destination / "10_cnn_glyphs.png"
    title, note = _STAGE_SPECS["10_cnn_glyphs.png"]
    try:
        model, charset, device = load_glyph_recognizer(weights)
    except (FileNotFoundError, ImportError, RuntimeError, OSError) as exc:
        return OcrStage("10_cnn_glyphs.png", title, cnn_path, str(exc)), (), [], [str(exc)]

    gate = load_content_gate(gate_mode)
    report_path = destination / "stage12_report.json"
    geometry = None
    if report_path.is_file():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        geometry = SheetGeometry.from_meta(payload.get("meta") or {}, report=payload)
    from chess_core.ocr.decode import CellDecoder
    from chess_core.ocr.roles import ROLE_BY_ID

    decoder = CellDecoder(notation_mode)
    reads: list[str] = []
    details: list[dict] = []
    tiles: list = []
    captions: list[str] = []
    for cell_path in cell_paths:
        split = segment_cell(cell_path)
        parsed = parse_cell_name(cell_path.name)
        row = None if parsed is None else parsed[1]
        col = None if parsed is None else parsed[2]
        gray = to_gray(cell_path)
        suspicions = inspect_cell_glyphs(split.glyphs)
        crop_decisions = []
        for glyph in split.glyphs:
            raw_crop = gray[glyph.box.y1 : glyph.box.y2, glyph.box.x1 : glyph.box.x2]
            crop_decisions.append(
                gate.decide_crop(raw_crop, sheet_geometry=geometry, row=row, col=col)
            )
        if not crop_decisions:
            crop_decisions.append(
                gate.decide_crop(gray, sheet_geometry=geometry, row=row, col=col)
            )
        cell_gate = gate.combine_glyph_decisions(tuple(crop_decisions[: max(len(split.glyphs), 1)]))
        guessed: list = []
        if split.glyphs:
            guessed = [("?", 0.0, ()) for _ in split.glyphs]
            keep_idx = [
                index
                for index, decision in enumerate(crop_decisions)
                if not decision.skip_cnn
            ]
            if keep_idx:
                tiles = [split.glyphs[index].mnist for index in keep_idx]
                predicted = predict_mnist_tiles(tiles, model, charset, device)
                for slot, item in zip(keep_idx, predicted):
                    char, score, alts = item
                    p = crop_decisions[slot].p_content
                    guessed[slot] = (
                        char,
                        score * p,
                        tuple((name, alt * p) for name, alt in alts),
                    )
        if cell_gate.cell_missing:
            text = "?"
        elif not guessed:
            text = "?"
        elif guessed[0][0] in ROLE_BY_ID:
            kept = [
                char
                for (char, _score, _alts), decision in zip(guessed, crop_decisions)
                if decision.accepted
            ]
            text = decoder.decode_roles(kept) if kept else "?"
        else:
            text = "".join(
                char
                for (char, _score, _alts), decision in zip(guessed, crop_decisions)
                if char != GARBAGE and decision.accepted
            ) or "?"
        reads.append(text if text else "?")
        glyphs = []
        for index, glyph in enumerate(split.glyphs):
            if index < len(guessed):
                char, score, alts = guessed[index]
            else:
                char, score, alts = "?", 0.0, ()
            decision = crop_decisions[index] if index < len(crop_decisions) else cell_gate
            suspicion = suspicions[index] if index < len(suspicions) else None
            tiles.append(glyph.mnist)
            captions.append(f"{char} {score:.2f}")
            glyphs.append(
                {
                    "char": char,
                    "role": char if char in ROLE_BY_ID else None,
                    "score": round(float(score), 4),
                    "alts": [[name, round(float(alt), 4)] for name, alt in alts[:5]],
                    "box": [glyph.box.x1, glyph.box.y1, glyph.box.x2, glyph.box.y2],
                    "p_content": round(float(decision.p_content), 4),
                    "gate_accepted": decision.accepted,
                    "gate_reason": decision.reason,
                    "seg_flag": None if suspicion is None else suspicion.seg_flag,
                    "seg_confidence": None if suspicion is None else suspicion.seg_confidence,
                }
            )
        content = split.content
        details.append(
            {
                "file": cell_path.name,
                "order": None if parsed is None else parsed[0],
                "row": None if parsed is None else parsed[1],
                "col": None if parsed is None else parsed[2],
                "expected_glyphs": split.expected,
                "n_glyphs": len(split.glyphs),
                "content_box": None
                if content is None
                else [content.x1, content.y1, content.x2, content.y2],
                "raw": text,
                "glyphs": glyphs,
                "gate_rejected": cell_gate.cell_missing,
                "p_content": round(float(cell_gate.p_content), 4),
                "gate_reason": cell_gate.reason,
                "gate_source": cell_gate.source,
                "gate_mode": gate.mode_name,
                "seg_flag": next((item.seg_flag for item in suspicions if item.seg_flag), None),
                "seg_confidence": max((item.seg_confidence for item in suspicions), default=0.0),
            }
        )
    saved = save_labeled_montage(tiles, captions, cnn_path)
    stage_note = f"{note}  ·  {device}  ·  gate={gate.mode_name}  ·  клеток {len(reads)}"
    stage = OcrStage(
        "10_cnn_glyphs.png",
        title,
        saved if saved is not None else cnn_path,
        stage_note,
    )
    return stage, tuple(reads), details, [f"cnn device={device}", f"gate={gate.mode_name}"]


def run_scoresheet_pipeline(
    image_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    prefer_external: bool = False,
    weights: Path | None = None,
    notation_mode: str = "ru",
    gate_mode: str = "soft",
) -> OcrRun:
    """Deskew, split, grid, MSER tiles, then CNN if weights exist."""

    del prefer_external
    source = Path(image_path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = Path(output_dir) if output_dir is not None else default_output_dir(source.stem)
    destination.mkdir(parents=True, exist_ok=True)

    stage12 = run_stage12_preprocess(source, destination)
    notes = list(stage12.notes)
    cnn_stage, cell_reads, cell_details, cnn_notes = _cnn_stage(
        stage12.cell_paths,
        destination,
        weights=weights,
        notation_mode=notation_mode,
        gate_mode=gate_mode,
    )
    from chess_core.app.experiments.ocr_eval import cell_metrics, load_sheet_truth
    from chess_core.app.experiments.ocr_language import constrain_cells
    from chess_core.ocr.gold import load_gold
    from chess_core.ocr.metrics import (
        format_confusion,
        glyph_confusion,
        pred_chars_from_details,
        role_report,
        sheet_metrics,
        write_report,
    )
    from chess_core.ocr.roles import hypothesize_notation

    from chess_core.ocr.decode import CellDecoder
    from chess_core.ocr.gate.attribution import oracle_table
    from chess_core.ocr.gate.integrity import flag_hits_against_gold
    from chess_core.ocr.hypothesis import CellHypothesis

    hypotheses = constrain_cells(cell_reads) if cell_reads else ()
    stamped: list = []
    for row, hypo in zip(cell_details, hypotheses):
        stamped.append(
            CellHypothesis(
                text=hypo.text,
                raw=hypo.raw,
                legal=hypo.legal,
                low_confidence=hypo.low_confidence or bool(row.get("gate_rejected")),
                reason="gate_reject" if row.get("gate_rejected") else hypo.reason,
                constraint=hypo.constraint,
                gate_rejected=bool(row.get("gate_rejected")),
                p_content=row.get("p_content"),
                seg_flag=row.get("seg_flag"),
                seg_confidence=row.get("seg_confidence"),
            )
        )
    hypotheses = tuple(stamped)
    legal_reads = tuple(item.text for item in hypotheses)
    for row, hypo in zip(cell_details, hypotheses):
        row["legal"] = hypo.text
        row["hypothesis"] = hypo.to_dict()
    gold = load_gold(source)
    truth = load_sheet_truth(source)
    legacy = cell_metrics(cell_reads, legal_reads, truth)
    measured = sheet_metrics(
        sheet_id=source.stem,
        gold=gold,
        raws=cell_reads,
        hypotheses=hypotheses,
        cell_details=cell_details,
    )
    pred_chars = pred_chars_from_details(cell_details)
    confusion = glyph_confusion(gold.chars, pred_chars) if gold is not None and gold.chars else {}
    predicted_roles = pred_chars
    roles_flat = [role_id for row in predicted_roles for role_id in row]
    notation_guess = hypothesize_notation(roles_flat)
    if notation_guess["notation_mode_hypothesis"] != notation_mode:
        notes.append(
            f"hypothesis notation={notation_guess['notation_mode_hypothesis']} "
            f"({notation_guess['reason']}); applied={notation_mode!r} via --notation"
        )
    roles_block = (
        role_report(gold.chars, predicted_roles)
        if gold is not None and gold.chars
        else role_report((), predicted_roles)
    )
    attribution = None
    seg_integrity = None
    if gold is not None and gold.plies and cell_details:
        attribution = oracle_table(
            gold,
            cell_details,
            hypotheses,
            CellDecoder(notation_mode),
        )
        if gold.chars:
            seg_integrity = flag_hits_against_gold(cell_details, gold.chars)
    metrics = {
        **legacy,
        **measured.to_dict(),
        "confusion": confusion,
        "hypotheses": [item.to_dict() for item in hypotheses],
        "notation_mode": notation_mode,
        "notation_hypothesis": notation_guess,
        **roles_block,
    }
    stages = _collect_stages(stage12, cnn_stage)
    notes.extend(cnn_notes)
    engine = "mser+cnn" if cell_reads else "mser"
    (destination / "glyphs.json").write_text(
        json.dumps(
            {
                "source": str(source),
                "engine": engine,
                "mnist_size": 28,
                "mnist_box": 20,
                "mnist_pad": "aspect kept (scale by max side), mass-centered on 28x28",
                "cells": [path.name for path in stage12.cell_paths],
                "cell_reads": list(cell_reads),
                "legal_reads": list(legal_reads),
                "cell_details": cell_details,
                "metrics": metrics,
                "report": str(destination / "report.json"),
                "grid_rows": stage12.grid_rows,
                "grid_cols": stage12.grid_cols,
                "occupied_cells": stage12.occupied_cells,
                "h_lines": stage12.h_lines,
                "v_lines": stage12.v_lines,
                "notation_mode": notation_mode,
                "notation_hypothesis": notation_guess,
                "notes": notes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_report(
        destination / "report.json",
        {
            "source": str(source),
            "engine": engine,
            "notation_mode": notation_mode,
            "notation_hypothesis": notation_guess,
            "metrics": measured.to_dict(),
            "confusion": confusion,
            "confusion_text": format_confusion(confusion),
            "role_confusion": roles_block["role_confusion"],
            "role_support": roles_block["role_support"],
            "max_class_share": roles_block["max_class_share"],
            "pairs_suspected": roles_block["pairs_suspected"],
            "cyrillic_role_share": roles_block["cyrillic_role_share"],
            "role_ids": roles_block["role_ids"],
            "gate_mode": gate_mode,
            "attribution": attribution,
            "seg_integrity": seg_integrity,
            "cell_reads": list(cell_reads),
            "legal_reads": list(legal_reads),
            "hypotheses": [item.to_dict() for item in hypotheses],
        },
    )
    print(format_confusion(confusion), flush=True)
    print(
        "metrics "
        f"coverage={measured.coverage:.3f} "
        f"raw_move_acc={measured.raw_move_acc:.3f} "
        f"legal_move_acc={measured.legal_move_acc:.3f} "
        f"n_gold={measured.n_gold} occupied={measured.n_occupied}",
        flush=True,
    )
    return OcrRun(
        source=source,
        output_dir=destination,
        stages=tuple(stages),
        moves=tuple(item.text for item in hypotheses if item.legal),
        pgn="\n".join(
            f"{index + 1}. {item.text}"
            for index, item in enumerate(item for item in hypotheses if item.legal)
        ),
        pgn_path=destination / "glyphs.json",
        engine=engine,
        notes=tuple(notes),
        grid_rows=stage12.grid_rows,
        grid_cols=stage12.grid_cols,
        occupied_cells=stage12.occupied_cells,
        h_lines=stage12.h_lines,
        v_lines=stage12.v_lines,
        cell_reads=cell_reads,
    )
