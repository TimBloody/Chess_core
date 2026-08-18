"""Subprocess lifecycle for external engines."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from typing import TextIO


@dataclass
class EngineProcess:
    command: list[str]
    _process: subprocess.Popen[str] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

    def stop(self) -> None:
        with self._lock:
            if self._process is None:
                return
            try:
                if self._process.stdin is not None:
                    self._process.stdin.write("quit\n")
                    self._process.stdin.flush()
            except OSError:
                pass
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    @property
    def stdin(self) -> TextIO | None:
        return None if self._process is None else self._process.stdin

    @property
    def stdout(self) -> TextIO | None:
        return None if self._process is None else self._process.stdout

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
