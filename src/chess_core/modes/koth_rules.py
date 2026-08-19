"""King of the Hill zone masks."""

from __future__ import annotations


def center_zone_mask(*, files: int = 8, ranks: int = 8) -> int:
    """Bitmask for the four central squares on an 8x8 board (d4, e4, d5, e5)."""
    del files, ranks  # fixed 8x8 centre; parameters reserved for future boards
    return (1 << 27) | (1 << 28) | (1 << 35) | (1 << 36)
