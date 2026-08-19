"""Non-blocking Qt bridge for engine analysis."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from chess_core.app.engine import (
    BestMove,
    EngineHintService,
    SearchLimit,
)
from chess_core.core.gamemode import GameMode
from chess_core.core.state import GameState


class _EngineWorker(QThread):
    finished_analysis = pyqtSignal(object)

    def __init__(
        self,
        service: EngineHintService,
        mode: GameMode,
        state: GameState,
        *,
        registry_id: str | None,
        limit: SearchLimit,
    ) -> None:
        super().__init__()
        self._service = service
        self._mode = mode
        self._state = state
        self._registry_id = registry_id
        self._limit = limit

    def run(self) -> None:
        result = self._service.analyze(
            self._mode,
            self._state,
            self._limit,
            registry_id=self._registry_id,
        )
        self.finished_analysis.emit(result)


class EngineBridge(QObject):
    analysis_ready = pyqtSignal(object)

    def __init__(
        self, service: EngineHintService, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._workers: list[_EngineWorker] = []
        self._generation = 0

    def is_busy(self) -> bool:
        return any(worker.isRunning() for worker in self._workers)

    def request_hint(
        self,
        mode: GameMode,
        state: GameState,
        *,
        registry_id: str | None = None,
        limit: SearchLimit | None = None,
    ) -> None:
        self._generation += 1
        generation = self._generation
        worker = _EngineWorker(
            self._service,
            mode,
            state,
            registry_id=registry_id,
            limit=limit or SearchLimit(),
        )
        self._workers.append(worker)
        worker.finished_analysis.connect(
            lambda result, gen=generation: self._on_finished(result, gen)
        )
        worker.finished.connect(lambda w=worker: self._forget_worker(w))
        worker.start()

    def _forget_worker(self, worker: _EngineWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def _on_finished(self, result: BestMove, generation: int) -> None:
        if generation != self._generation:
            return
        self.analysis_ready.emit(result)
