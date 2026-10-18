"""Subprocess lifecycle for external engines."""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


def hidden_popen_kwargs() -> dict[str, object]:
    """Start engine binaries without a flashing Windows console."""
    kwargs: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "bufsize": 1,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    return kwargs


@dataclass
class EngineProcess:
    command: list[str]
    cwd: str | None = None
    _process: subprocess.Popen[str] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            workdir = self.cwd
            if workdir is None and self.command:
                parent = Path(self.command[0]).resolve().parent
                if parent.is_dir():
                    workdir = str(parent)
            self._process = subprocess.Popen(
                self.command,
                cwd=workdir,
                **hidden_popen_kwargs(),
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
