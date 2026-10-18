"""One cell's decode result. Text is never empty."""

from __future__ import annotations

from dataclasses import dataclass

MISSING_MOVE = "?"


@dataclass(frozen=True, slots=True)
class CellHypothesis:
    """Best available reading for an occupied scoresheet cell."""

    text: str
    raw: str
    legal: bool
    low_confidence: bool
    reason: str
    constraint: str
    gate_rejected: bool = False
    p_content: float | None = None
    seg_flag: str | None = None
    seg_confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("CellHypothesis.text must not be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "raw": self.raw,
            "legal": self.legal,
            "low_confidence": self.low_confidence,
            "reason": self.reason,
            "constraint": self.constraint,
            "gate_rejected": self.gate_rejected,
            "p_content": self.p_content,
            "seg_flag": self.seg_flag,
            "seg_confidence": self.seg_confidence,
        }


def nonempty_raw(raw: str) -> str:
    text = "".join(raw.split())
    return text if text else MISSING_MOVE
