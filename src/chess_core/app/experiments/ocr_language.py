"""Map noisy glyph strings onto legal SAN from the current position."""

from __future__ import annotations

from chess_core.app.game import LocalGameService
from chess_core.core.move import MoveAction, Turn
from chess_core.core.notation import NotationStyle, format_action, square_name
from chess_core.modes.chess import classic_chess
from chess_core.ocr.hypothesis import CellHypothesis, nonempty_raw


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, char in enumerate(left, start=1):
        row = [i]
        for j, other in enumerate(right, start=1):
            ins = row[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (char != other)
            row.append(min(ins, delete, sub))
        prev = row
    return prev[-1]


def normalize_read(text: str) -> str:
    return "".join(text.split())


def _aliases(action: MoveAction, before, after) -> set[str]:
    main = format_action(
        action, before=before, after=after, style=NotationStyle.PIECE_SQUARE
    )
    names = {main, main.replace("x", "")}
    piece = before.board_state.piece_at(
        action.from_square.index(before.board_state.board.shape.files)
    )
    target = square_name(action.to_square)
    if piece is not None and piece.piece_type.name == "pawn":
        origin = square_name(action.from_square)
        names.add(target)
        names.add(f"{origin[0]}{target}")
        names.add(f"{origin[0]}x{target}")
        names.add(f"x{target}")
    files = before.board_state.board.shape.files
    if piece is not None and piece.piece_type.name == "king":
        delta = abs(action.to_square.file - action.from_square.file)
        if delta == 2:
            names.update({"O-O", "OO", "0-0"} if action.to_square.file > action.from_square.file else {"O-O-O", "OOO", "0-0-0"})
    del files
    return names


def legal_catalog(service: LocalGameService) -> list[tuple[str, MoveAction, set[str]]]:
    before = service.state
    rows: list[tuple[str, MoveAction, set[str]]] = []
    for move in service.legal_moves():
        after = before.apply_turn(Turn(before.side_to_move, [move]), record_history=False)
        text = format_action(move, before=before, after=after, style=NotationStyle.PIECE_SQUARE)
        rows.append((text, move, _aliases(move, before, after)))
    return rows


def pick_legal_san(raw: str, catalog: list[tuple[str, MoveAction, set[str]]]) -> tuple[str, int] | None:
    needle = normalize_read(raw)
    if len(needle) < 2 or not catalog:
        return None
    scored: list[tuple[str, int]] = []
    for san, _move, aliases in catalog:
        options = {san, *(alias for alias in aliases)}
        dist = min(levenshtein(needle, option) for option in options)
        dist = min(dist, levenshtein(needle.lower(), san.lower()))
        scored.append((san, dist))
    if not scored:
        return None
    best_dist = min(item[1] for item in scored)
    tied = sorted({san for san, dist in scored if dist == best_dist})
    if len(tied) != 1:
        return None
    if best_dist > (1 if len(needle) <= 3 else 2):
        return None
    return tied[0], best_dist


def constrain_cells(raws: tuple[str, ...]) -> tuple[CellHypothesis, ...]:
    """Filter each cell through legal SAN. Never emit an empty string.

    A unique legal snap is played and returned. Otherwise the best raw
    candidate is kept with ``low_confidence`` — the game state does not move.
    """

    service = LocalGameService(classic_chess())
    out: list[CellHypothesis] = []
    for raw in raws:
        fallback = nonempty_raw(normalize_read(raw))
        catalog = legal_catalog(service)
        picked = pick_legal_san(raw, catalog)
        if picked is None:
            out.append(
                CellHypothesis(
                    text=fallback,
                    raw=raw,
                    legal=False,
                    low_confidence=True,
                    reason="no_legal_match",
                    constraint="raw_fallback",
                )
            )
            continue
        san, dist = picked
        move = next(item[1] for item in catalog if item[0] == san)
        if move not in service.legal_moves():
            out.append(
                CellHypothesis(
                    text=fallback,
                    raw=raw,
                    legal=False,
                    low_confidence=True,
                    reason="snap_not_playable",
                    constraint="raw_fallback",
                )
            )
            continue
        service.play(move)
        out.append(
            CellHypothesis(
                text=san,
                raw=raw,
                legal=True,
                low_confidence=dist > 0 or normalize_read(raw) != san,
                reason="legal_snap" if dist else "legal_exact",
                constraint="legal",
            )
        )
    return tuple(out)


def constrain_cell_reads(raws: tuple[str, ...]) -> tuple[str, ...]:
    """Walk from the start position. Texts are never empty."""

    return tuple(item.text for item in constrain_cells(raws))
