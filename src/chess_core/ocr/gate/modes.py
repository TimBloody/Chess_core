"""Gate application strategies. Constructed once; the pipeline does not branch on mode names."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


SOFT_REJECT = 0.5


@dataclass(frozen=True, slots=True)
class ModeDecision:
    accepted: bool
    skip_cnn: bool
    cell_missing: bool
    reason: str


class GateMode(ABC):
    name: str

    @abstractmethod
    def apply(self, p_content: float) -> ModeDecision:
        raise NotImplementedError

    def emit_p(self, p_content: float) -> float:
        """Probability the rest of the pipeline sees. Off is identity (1.0)."""
        return p_content


class OffMode(GateMode):
    name = "off"

    def apply(self, p_content: float) -> ModeDecision:
        del p_content
        return ModeDecision(True, False, False, "off")

    def emit_p(self, p_content: float) -> float:
        del p_content
        return 1.0


class SoftMode(GateMode):
    name = "soft"

    def apply(self, p_content: float) -> ModeDecision:
        if p_content < SOFT_REJECT:
            return ModeDecision(False, False, True, "soft_reject")
        return ModeDecision(True, False, False, "soft_keep")


class HardMode(GateMode):
    name = "hard"

    def apply(self, p_content: float) -> ModeDecision:
        if p_content < SOFT_REJECT:
            return ModeDecision(False, True, True, "hard_reject")
        return ModeDecision(True, False, False, "hard_keep")


GATE_MODES: dict[str, type[GateMode]] = {
    "off": OffMode,
    "soft": SoftMode,
    "hard": HardMode,
}


def make_mode(name: str) -> GateMode:
    if name not in GATE_MODES:
        raise ValueError(f"gate mode must be off|soft|hard, got {name!r}")
    return GATE_MODES[name]()
