"""ContentGate: geometry, then heuristic, optional tiny model. Modes are objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from chess_core.infra.paths import project_root
from chess_core.ocr.gate.calibration import platt_apply
from chess_core.ocr.gate.features import extract_raw_features, gate_vector
from chess_core.ocr.gate.geometry import GeometryPrefilter, SheetGeometry
from chess_core.ocr.gate.heuristic import HeuristicGate, load_thresholds
from chess_core.ocr.gate.modes import GateMode, make_mode


@dataclass(frozen=True, slots=True)
class GateDecision:
    p_content: float
    accepted: bool
    skip_cnn: bool
    cell_missing: bool
    reason: str
    source: str
    features: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "p_content": self.p_content,
            "accepted": self.accepted,
            "skip_cnn": self.skip_cnn,
            "cell_missing": self.cell_missing,
            "reason": self.reason,
            "source": self.source,
            "features": self.features,
        }


class ContentGate:
    def __init__(
        self,
        mode: GateMode,
        heuristic: HeuristicGate,
        geometry: GeometryPrefilter,
        model: Any | None = None,
        platt: tuple[float, float] | None = None,
    ) -> None:
        self.mode = mode
        self.heuristic = heuristic
        self.geometry = geometry
        self.model = model
        self.platt = platt

    @property
    def mode_name(self) -> str:
        return self.mode.name

    def decide_crop(
        self,
        image: np.ndarray,
        *,
        sheet_geometry: SheetGeometry | None = None,
        row: int | None = None,
        col: int | None = None,
    ) -> GateDecision:
        if sheet_geometry is not None:
            zone = self.geometry.zone(sheet_geometry, row=row, col=col)
            if zone is not None:
                return self._finish(0.05, zone, "geometry", {})
        features = extract_raw_features(image)
        p_h, why = self.heuristic.score(features)
        p = p_h
        source = "heuristic"
        if self.model is not None:
            vec = gate_vector(image).reshape(1, -1)
            expected = int(getattr(self.model, "n_features", vec.size))
            if expected == 7:
                vec = features.vector().reshape(1, -1)
            p_m = float(self.model.predict_proba(vec)[0, 1])
            p = max(p_h, p_m)
            source = "ensemble"
        if self.platt is not None:
            p = float(platt_apply(np.asarray([p], dtype=np.float64), *self.platt)[0])
        return self._finish(p, why, source, features.to_dict())

    def _finish(self, p: float, why: str, source: str, features: dict[str, float]) -> GateDecision:
        applied = self.mode.apply(p)
        return GateDecision(
            p_content=self.mode.emit_p(p),
            accepted=applied.accepted,
            skip_cnn=applied.skip_cnn,
            cell_missing=applied.cell_missing,
            reason=why if applied.accepted else applied.reason,
            source=source,
            features=features,
        )

    def combine_glyph_decisions(self, decisions: tuple[GateDecision, ...]) -> GateDecision:
        if not decisions:
            return self._finish(0.1, "empty", "heuristic", {})
        best = max(decisions, key=lambda item: item.p_content)
        applied = self.mode.apply(best.p_content)
        return GateDecision(
            self.mode.emit_p(best.p_content),
            applied.accepted,
            applied.skip_cnn,
            applied.cell_missing,
            best.reason if applied.accepted else applied.reason,
            best.source,
            best.features,
        )


def thresholds_path() -> Path:
    return project_root() / "data" / "gate" / "thresholds.json"


def model_path() -> Path:
    return project_root() / "data" / "gate" / "gate_model.json"


def load_content_gate(mode: str = "soft") -> ContentGate:
    heuristic = HeuristicGate(load_thresholds(thresholds_path()))
    model = _load_optional_model(model_path())
    platt = _load_optional_platt(project_root() / "data" / "gate" / "calibration.json")
    return ContentGate(make_mode(mode), heuristic, GeometryPrefilter(), model, platt)


def _load_optional_model(path: Path) -> Any | None:
    if not path.is_file():
        return None
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    weights = np.asarray(payload["weights"], dtype=np.float64)
    bias = float(payload["bias"])
    mean = np.asarray(payload["mean"], dtype=np.float64)
    std = np.asarray(payload["std"], dtype=np.float64)

    class _Logit:
        n_features = int(len(weights))

        def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
            z = ((matrix - mean) / np.maximum(std, 1e-6)) @ weights + bias
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -20, 20)))
            p = np.clip(p, 1e-6, 1 - 1e-6)
            return np.column_stack((1.0 - p, p))

    return _Logit()


def _load_optional_platt(path: Path) -> tuple[float, float] | None:
    if not path.is_file():
        return None
    payload = __import__("json").loads(path.read_text(encoding="utf-8"))
    if not payload.get("apply"):
        return None
    return float(payload["a"]), float(payload["b"])
