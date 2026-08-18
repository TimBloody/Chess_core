"""Bit masks for cells and piece occupancy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BitMask:
    """Single integer bitmask over board cells."""

    value: int

    def __and__(self, other: BitMask) -> BitMask:
        return BitMask(self.value & other.value)

    def __or__(self, other: BitMask) -> BitMask:
        return BitMask(self.value | other.value)

    def __invert__(self) -> BitMask:
        return BitMask(~self.value)

    def intersect(self, other: BitMask) -> BitMask:
        return self & other

    def union(self, other: BitMask) -> BitMask:
        return self | other

    def without(self, other: BitMask) -> BitMask:
        return BitMask(self.value & ~other.value)


class BitboardSet:
    """Named masks per square or per piece placement context."""

    def __init__(self) -> None:
        self._masks: dict[str, int] = {}

    def set_mask(self, key: str, mask: int) -> None:
        self._masks[key] = mask

    def get_mask(self, key: str) -> int:
        return self._masks[key]

    def mask_for_square(self, square_index: int) -> int:
        if square_index < 0:
            raise ValueError("square_index must be non-negative")

        return 1 << square_index
