"""UCI protocol client."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from chess_core.infra.engines.process import EngineProcess


@dataclass(frozen=True, slots=True)
class UciInfo:
    score_cp: int | None = None
    mate_in: int | None = None
    pv: tuple[str, ...] = ()
    depth: int | None = None


class UciClient:
    def __init__(self, executable: str, *, movetime_ms: int = 500) -> None:
        exe = Path(executable)
        self._process = EngineProcess([str(exe)], cwd=str(exe.parent))
        self._movetime_ms = movetime_ms

    def handshake(self) -> None:
        self._process.start()
        self._write("uci")
        self._wait_for("uciok", timeout=5.0)
        self._write("isready")
        self._wait_for("readyok", timeout=5.0)

    def analyze_fen(self, fen: str) -> tuple[str | None, UciInfo | None]:
        self._write(f"position fen {fen}")
        self._write(f"go movetime {self._movetime_ms}")
        return self._collect_bestmove()

    def shutdown(self) -> None:
        self._process.stop()

    def _collect_bestmove(self) -> tuple[str | None, UciInfo | None]:
        bestmove: str | None = None
        last_info: UciInfo | None = None
        deadline = time.monotonic() + self._movetime_ms / 1000 + 5.0
        stdout = self._process.stdout
        if stdout is None:
            return None, None
        while time.monotonic() < deadline:
            line = stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    bestmove = parts[1]
                break
            info = self._parse_info(line)
            if info is not None:
                last_info = info
        return bestmove, last_info

    def _write(self, command: str) -> None:
        stdin = self._process.stdin
        if stdin is None:
            raise RuntimeError("engine process is not running")
        stdin.write(command + "\n")
        stdin.flush()

    def _wait_for(self, token: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        stdout = self._process.stdout
        if stdout is None:
            raise RuntimeError("engine process is not running")
        while time.monotonic() < deadline:
            line = stdout.readline()
            if token in line:
                return
        raise TimeoutError(f"engine did not respond with {token!r}")

    def _parse_info(self, line: str) -> UciInfo | None:
        if not line.startswith("info "):
            return None
        score_cp = None
        mate_in = None
        depth = None
        pv: list[str] = []
        if match := re.search(r"score cp (-?\d+)", line):
            score_cp = int(match.group(1))
        if match := re.search(r"score mate (-?\d+)", line):
            mate_in = int(match.group(1))
        if match := re.search(r"depth (\d+)", line):
            depth = int(match.group(1))
        if " pv " in line:
            pv = line.split(" pv ", 1)[1].split()
        return UciInfo(score_cp=score_cp, mate_in=mate_in, pv=tuple(pv), depth=depth)
