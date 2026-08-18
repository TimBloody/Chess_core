"""Chess clock display widget (presentation only)."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chess_core.app.clock import ClockSnapshot
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlKind


class GameClockWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._white = QLabel("10:00")
        self._black = QLabel("10:00")
        self._mode = QLabel("")
        layout = QVBoxLayout(self)
        layout.addWidget(self._black)
        layout.addWidget(self._mode)
        layout.addWidget(self._white)

    def set_snapshot(
        self,
        snapshot: ClockSnapshot | None,
        *,
        client_mono_ms: int | None = None,
    ) -> None:
        if snapshot is None:
            self._white.setText("--:--")
            self._black.setText("--:--")
            self._mode.setText("")
            return
        elapsed = 0
        if client_mono_ms is not None and snapshot.running_side is not None:
            elapsed = max(0, client_mono_ms - snapshot.server_mono_ms)
        white_ms = snapshot.white_remaining_ms
        black_ms = snapshot.black_remaining_ms
        if snapshot.running_side is PieceSide.WHITE:
            white_ms = max(0, white_ms - elapsed)
        elif snapshot.running_side is PieceSide.BLACK:
            black_ms = max(0, black_ms - elapsed)
        self._white.setText(self._format_ms(white_ms))
        self._black.setText(self._format_ms(black_ms))
        kind = snapshot.time_control.kind
        label = {
            TimeControlKind.SIMPLE: "Sudden death",
            TimeControlKind.FISCHER: "Fischer",
            TimeControlKind.BRONSTEIN: "Bronstein",
            TimeControlKind.BYOYOMI: "Byoyomi",
        }[kind]
        self._mode.setText(label)

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(0, value) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"
