"""Whole-cell reader. The cell rectangle is not cut into MSER glyphs.

This is an experiment beside glyph_cnn.pt. It must not replace that file.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from chess_core.ocr.candidates import MoveCandidate, ensure_sorted
from chess_core.ocr.decode import CellDecoder
from chess_core.ocr.move_norm import normalize_move_text, original_ink
from chess_core.ocr.roles import ROLE_IDS

INPUT_H = 32
INPUT_W = 128
MAX_LABEL_LEN = 8
BLANK = 0


def time_steps(height: int = INPUT_H, width: int = INPUT_W) -> int:
    """Width after the pools. Must be at least the longest move string."""

    if height != INPUT_H or width != INPUT_W:
        raise ValueError("geometry is fixed at 32x128 so the test matches the network")
    h, w = height, width
    h, w = h // 2, w // 2
    h, w = h // 2, w // 2
    h = h // 2
    h = h // 4
    if h != 1:
        raise RuntimeError(f"cell CNN height collapsed to {h}, expected 1")
    return w


def prepare_cell_image(gray: np.ndarray) -> np.ndarray:
    """Keep aspect, fix height, pad on the right. No glyph cuts."""

    import cv2

    image = np.asarray(gray)
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if image.size == 0:
        return np.full((INPUT_H, INPUT_W), 255, dtype=np.uint8)
    height, width = image.shape[:2]
    new_w = max(1, int(round(width * (INPUT_H / max(height, 1)))))
    interpolation = cv2.INTER_AREA if new_w < width else cv2.INTER_CUBIC
    resized = cv2.resize(image, (new_w, INPUT_H), interpolation=interpolation)
    canvas = np.full((INPUT_H, INPUT_W), 255, dtype=np.uint8)
    copy_w = min(INPUT_W, resized.shape[1])
    canvas[:, :copy_w] = resized[:, :copy_w]
    return canvas


def build_cell_ctc(torch_module, n_roles: int = len(ROLE_IDS)):
    """CNN over the cell, then a bidirectional LSTM. Blank class is index 0."""

    torch = torch_module
    nn = torch.nn

    class CellCTC(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d((2, 1)),
                nn.Conv2d(64, 64, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d((4, 1)),
            )
            self.rnn = nn.LSTM(64, 64, num_layers=1, bidirectional=True)
            self.fc = nn.Linear(128, n_roles + 1)

        def forward(self, images):
            features = self.conv(images)
            if features.shape[2] != 1:
                raise RuntimeError(f"expected height 1 after conv, got {tuple(features.shape)}")
            sequence = features.squeeze(2).permute(2, 0, 1)
            encoded, _state = self.rnn(sequence)
            return self.fc(encoded)

    return CellCTC()


def greedy_roles(log_probs) -> tuple[str, ...]:
    """log_probs is T x C, blank = 0."""

    chosen = log_probs.argmax(dim=-1).tolist()
    roles: list[str] = []
    previous = BLANK
    for index in chosen:
        if index != BLANK and index != previous:
            role_index = int(index) - 1
            if 0 <= role_index < len(ROLE_IDS):
                roles.append(ROLE_IDS[role_index])
        previous = int(index)
    return tuple(roles)


def candidates_from_log_probs(
    log_probs,
    decoder: CellDecoder,
    *,
    k: int,
) -> tuple[MoveCandidate, ...]:
    """Greedy top-1 plus the next class at the greedy frames, sorted by score.

    A full CTC beam is not required to check the head. Scores stay with the raw string.
    """

    if k < 1:
        return ()
    roles = greedy_roles(log_probs)
    frame = log_probs.argmax(dim=-1)
    greedy_score = float(log_probs[range(log_probs.shape[0]), frame].sum())
    found = [
        MoveCandidate(
            raw=original_ink(decoder.decode_roles(roles)),
            normalized=normalize_move_text(decoder.decode_roles(roles)),
            log_score=greedy_score,
            roles=roles,
        )
    ]
    seen = {found[0].raw}
    flat = log_probs.reshape(-1)
    order = flat.argsort(descending=True).tolist()
    for flat_index in order:
        if len(found) >= k:
            break
        time = int(flat_index) // int(log_probs.shape[1])
        cls = int(flat_index) % int(log_probs.shape[1])
        if cls == BLANK or cls == int(frame[time]):
            continue
        alt = list(roles)
        role_index = cls - 1
        if not 0 <= role_index < len(ROLE_IDS):
            continue
        # One-frame swap is only a diverse candidate, not a claimed posterior mode.
        if alt:
            alt[min(time, len(alt) - 1)] = ROLE_IDS[role_index]
        else:
            alt = [ROLE_IDS[role_index]]
        text = decoder.decode_roles(alt)
        if text in seen:
            continue
        seen.add(text)
        found.append(
            MoveCandidate(
                raw=original_ink(text),
                normalized=normalize_move_text(text),
                log_score=greedy_score - len(found),
                roles=tuple(alt),
            )
        )
    return ensure_sorted(found[:k])


def roles_to_ctc_target(roles: Sequence[str]) -> list[int]:
    return [ROLE_IDS.index(role) + 1 for role in roles]
