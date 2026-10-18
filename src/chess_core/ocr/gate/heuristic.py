"""Untrained content rules on raw features. Thresholds come from train sheets only."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json

from chess_core.ocr.gate.features import RawFeatures


@dataclass(frozen=True, slots=True)
class HeuristicThresholds:
    t_elongation: float = 12.0
    t_aspect: float = 3.5
    t_bbox_fill_line: float = 0.35
    t_ink_junk: float = 0.012
    t_bbox_junk: float = 0.04
    t_edge_hug: float = 0.72
    t_curvature: float = 0.35

    def to_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}

    @classmethod
    def from_dict(cls, payload: dict[str, float]) -> "HeuristicThresholds":
        known = {key: float(payload[key]) for key in asdict(cls()).keys() if key in payload}
        return cls(**known)


class HeuristicGate:
    """Reject only when the crop is clearly a line, crumb, or frame hug."""

    def __init__(self, thresholds: HeuristicThresholds | None = None) -> None:
        self.thresholds = thresholds or HeuristicThresholds()

    def score(self, features: RawFeatures) -> tuple[float, str]:
        thr = self.thresholds
        glyph_like = (
            features.ink_ratio >= 0.012
            and features.elongation < max(8.0, thr.t_elongation * 0.7)
            and features.stroke_width < 8.0
        )
        if glyph_like:
            p = 0.60 + 0.39 * min(1.0, features.ink_ratio / 0.18)
            return float(min(0.99, p)), "content"
        if features.ink_ratio < thr.t_ink_junk and features.bbox_fill < thr.t_bbox_junk:
            return 0.12, "junk"
        if features.elongation > thr.t_elongation or (
            features.aspect > thr.t_aspect and features.bbox_fill > thr.t_bbox_fill_line
        ):
            return 0.18, "line"
        if features.edge_hug > thr.t_edge_hug and features.curvature_proxy < thr.t_curvature:
            return 0.22, "edge"
        p = 0.55 + 0.45 * min(1.0, features.ink_ratio / 0.18)
        if features.edge_hug > 0.5:
            p *= 0.85
        return float(min(0.99, max(0.51, p))), "content"

    def p_content(self, features: RawFeatures) -> float:
        return self.score(features)[0]


def save_thresholds(path: Path, thresholds: HeuristicThresholds) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(thresholds.to_dict(), indent=2), encoding="utf-8")


def load_thresholds(path: Path) -> HeuristicThresholds:
    if not path.is_file():
        return HeuristicThresholds()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HeuristicThresholds.from_dict(payload)
