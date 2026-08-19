"""Play short WAV cues from ``assets/sounds``. Missing files are ignored."""

from __future__ import annotations

from pathlib import Path

from chess_core.app.sound import SoundEvent
from chess_core.infra.paths import assets_root
from chess_core.ui.assets_loader import AssetsLoader

try:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - optional Qt multimedia
    QSoundEffect = None  # type: ignore[misc, assignment]
    QUrl = None  # type: ignore[misc, assignment]


class SoundPlayer:
    """UI adapter: maps ``SoundEvent`` to ``assets/sounds/{name}.wav``."""

    def __init__(self, assets: AssetsLoader | None = None) -> None:
        self._root = (assets.assets_root if assets is not None else assets_root()) / "sounds"
        self._effects: dict[SoundEvent, object] = {}
        self._accent: object | None = None

    def play(self, event: SoundEvent, *, accent: SoundEvent | None = None) -> None:
        self._play_on(event, overlay=False)
        if accent is not None and accent is not event:
            self._play_on(accent, overlay=True)

    def _play_on(self, event: SoundEvent, *, overlay: bool) -> None:
        if QSoundEffect is None or QUrl is None:
            return
        path = self._root / event.filename
        if not path.is_file():
            return
        effect = self._effect(event, overlay=overlay, path=path)
        effect.play()

    def _effect(self, event: SoundEvent, *, overlay: bool, path: Path):
        if overlay:
            if self._accent is None:
                self._accent = QSoundEffect()
            effect = self._accent
        else:
            effect = self._effects.get(event)
            if effect is None:
                effect = QSoundEffect()
                self._effects[event] = effect
        effect.setSource(QUrl.fromLocalFile(str(path.resolve())))
        effect.setVolume(0.65)
        return effect
