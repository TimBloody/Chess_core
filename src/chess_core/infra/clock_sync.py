"""Client-side clock projection from server snapshots."""

from __future__ import annotations

from chess_core.app.clock import ClockSnapshot
from chess_core.core.piece import PieceSide


class ClockProjection:
    """Interpolate display time locally between server pushes."""

    def __init__(self) -> None:
        self._snapshot: ClockSnapshot | None = None
        self._anchor_client_ms: int = 0
        self._offset_ms: int = 0

    def apply_snapshot(self, snapshot: ClockSnapshot, *, client_mono_ms: int) -> None:
        self._snapshot = snapshot
        self._anchor_client_ms = client_mono_ms
        self._offset_ms = client_mono_ms - snapshot.server_mono_ms

    @property
    def revision(self) -> int:
        return self._snapshot.revision if self._snapshot else 0

    def display_ms(self, side: PieceSide, *, client_mono_ms: int) -> int:
        if self._snapshot is None:
            return 0
        base = (
            self._snapshot.white_remaining_ms
            if side is PieceSide.WHITE
            else self._snapshot.black_remaining_ms
        )
        if self._snapshot.running_side is None:
            return base
        if self._snapshot.running_side is not side:
            return base
        elapsed = client_mono_ms - self._anchor_client_ms
        return max(0, base - elapsed)

    def should_request_heartbeat(self, *, client_mono_ms: int, interval_ms: int = 12_000) -> bool:
        if self._snapshot is None:
            return True
        return client_mono_ms - self._snapshot.server_mono_ms > interval_ms
