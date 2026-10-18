"""Chess clock display widgets (presentation only)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from chess_core.app.clock import ClockSnapshot
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig, TimeControlKind

_TIME_PX = 32
_WHITE_BG = QColor(236, 232, 220)
_BLACK_BG = QColor(42, 46, 54)
_WHITE_FG = QColor(32, 32, 32)
_BLACK_FG = QColor(245, 245, 245)
_WHITE_BORDER = QColor(170, 162, 140)
_BLACK_BORDER = QColor(90, 96, 108)
_ACTIVE_BORDER = QColor(232, 176, 64)
_LOW_MS = 20_000
_LOW_BG = QColor(176, 48, 48)
_LOW_FG = QColor(255, 245, 245)
_KIND_CAPTIONS = {
    TimeControlKind.NONE: "Без времени",
    TimeControlKind.SIMPLE: "Контроль",
    TimeControlKind.FISCHER: "Фишер",
    TimeControlKind.BRONSTEIN: "Бронштейн",
    TimeControlKind.BYOYOMI: "Байоми",
}


class PlayerClockWidget(QFrame):
    """One player's clock, large enough to read from across the board."""

    clicked = pyqtSignal()

    def __init__(self, side: PieceSide, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._side = side
        self._time = QLabel("10:00")
        self._caption = QLabel("Белые" if side is PieceSide.WHITE else "Чёрные")
        font = QFont(self._time.font())
        font.setPixelSize(_TIME_PX)
        font.setBold(True)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._time.setFont(font)
        self._time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._time.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._caption.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._time.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(2)
        self.setMidLineWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        layout.addWidget(self._caption)
        layout.addWidget(self._time)
        self.setMinimumWidth(128)
        self.setMinimumHeight(72)
        self._apply_idle_colors()

    @property
    def side(self) -> PieceSide:
        return self._side

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def apply_snapshot(
        self,
        snapshot: ClockSnapshot | None,
        *,
        client_mono_ms: int | None = None,
    ) -> None:
        if snapshot is None:
            self._time.setText("--:--")
            self._set_running(False, low=False)
            return
        elapsed = 0
        if client_mono_ms is not None and snapshot.running_side is not None:
            elapsed = max(0, client_mono_ms - snapshot.server_mono_ms)
        remaining = (
            snapshot.white_remaining_ms
            if self._side is PieceSide.WHITE
            else snapshot.black_remaining_ms
        )
        if snapshot.running_side is self._side:
            remaining = max(0, remaining - elapsed)
        self._time.setText(self._format_ms(remaining))
        self._set_running(snapshot.running_side is self._side, low=remaining < _LOW_MS)

    def _set_running(self, running: bool, *, low: bool = False) -> None:
        if self._side is PieceSide.WHITE:
            bg, fg, idle_border = _WHITE_BG, _WHITE_FG, _WHITE_BORDER
        else:
            bg, fg, idle_border = _BLACK_BG, _BLACK_FG, _BLACK_BORDER
        if low:
            bg, fg = _LOW_BG, _LOW_FG
        border = _ACTIVE_BORDER if running else idle_border
        width = 3 if running else 1
        # Stylesheet must set QLabel color: a QFrame stylesheet otherwise
        # ignores the palette, leaving dark text on the black clock.
        self.setStyleSheet(
            f"PlayerClockWidget {{"
            f" background-color: {bg.name()};"
            f" color: {fg.name()};"
            f" border: {width}px solid {border.name()};"
            f" border-radius: 8px;"
            f"}}"
            f" PlayerClockWidget QLabel {{"
            f" color: {fg.name()};"
            f" background-color: transparent;"
            f"}}"
        )

    def _apply_idle_colors(self) -> None:
        self._set_running(False)

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(0, value) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"


class GameClockWidget(QWidget):
    """Composite of both player clocks; used by tests and optional stacked views."""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings_enabled = False
        self.white_clock = PlayerClockWidget(PieceSide.WHITE)
        self.black_clock = PlayerClockWidget(PieceSide.BLACK)
        self._white = self.white_clock._time
        self._black = self.black_clock._time
        self._mode = QLabel("")
        self._mode.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode.setObjectName("panelTitle")
        self._mode.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.addWidget(self.black_clock)
        layout.addWidget(self._mode)
        layout.addWidget(self.white_clock)
        self.white_clock.clicked.connect(self._forward_click)
        self.black_clock.clicked.connect(self._forward_click)

    @property
    def settings_enabled(self) -> bool:
        return self._settings_enabled

    def set_settings_enabled(self, enabled: bool) -> None:
        self._settings_enabled = enabled
        cursor = Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        tip = "Нажмите, чтобы настроить контроль времени" if enabled else ""
        for widget in (self, self.white_clock, self.black_clock):
            widget.setCursor(cursor)
            widget.setToolTip(tip)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._forward_click()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._forward_click()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_snapshot(
        self,
        snapshot: ClockSnapshot | None,
        *,
        client_mono_ms: int | None = None,
    ) -> None:
        self.white_clock.apply_snapshot(snapshot, client_mono_ms=client_mono_ms)
        self.black_clock.apply_snapshot(snapshot, client_mono_ms=client_mono_ms)
        if snapshot is None:
            self._mode.setText("")
            return
        self._mode.setText(_control_caption(snapshot.time_control))

    def _forward_click(self) -> None:
        if self._settings_enabled:
            self.clicked.emit()


def _control_caption(config: TimeControlConfig) -> str:
    kind = _KIND_CAPTIONS[config.kind]
    if not config.is_timed:
        return kind
    return f"{kind} {config.main_minutes}+{config.extra_seconds}"
