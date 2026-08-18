"""Non-blocking Qt bridge for engine analysis."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from chess_core.app.engine import BestMove, EngineAnalysisService, EngineRequest


class _EngineWorker(QThread):
    finished_analysis = pyqtSignal(object)

    def __init__(self, service: EngineAnalysisService, request: EngineRequest) -> None:
        super().__init__()
        self._service = service
        self._request = request

    def run(self) -> None:
        result = self._service.analyze(self._request)
        self.finished_analysis.emit(result)


class EngineBridge(QObject):
    analysis_ready = pyqtSignal(object)

    def __init__(self, service: EngineAnalysisService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._worker: _EngineWorker | None = None

    def request_analysis(self, request: EngineRequest) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(100)
        self._worker = _EngineWorker(self._service, request)
        self._worker.finished_analysis.connect(self._on_finished)
        self._worker.start()

    def _on_finished(self, result: BestMove) -> None:
        self.analysis_ready.emit(result)
