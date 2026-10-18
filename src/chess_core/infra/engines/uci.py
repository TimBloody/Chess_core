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
    def __init__(
        self,
        executable: str,
        *,
        movetime_ms: int = 500,
        depth: int | None = None,
        options: dict[str, str] | None = None,
    ) -> None:
        cwd = str(Path(executable).resolve().parent) if executable else None
        self._process = EngineProcess([executable], cwd=cwd)
        self._movetime_ms = movetime_ms
        self._depth = depth
        self._options = dict(options or {})
        self._hello = "uci"
        self._hello_token = "uciok"
        self._newgame = "ucinewgame"
        self._ready_timeout = 8.0
        self._handshook = False

    def handshake(self) -> None:
        self._process.start()
        if self._handshook and self._process.is_running():
            return
        self._write(self._hello)
        self._wait_for(self._hello_token, timeout=8.0)
        for name, value in self._options.items():
            self._write(f"setoption name {name} value {value}")
        self._write(self._newgame)
        self._write("isready")
        self._wait_for("readyok", timeout=self._ready_timeout)
        self._handshook = True

    def analyze_fen(
        self,
        fen: str,
        *,
        movetime_ms: int | None = None,
        depth: int | None = None,
    ) -> tuple[str | None, UciInfo | None]:
        self.handshake()
        previous = (self._movetime_ms, self._depth)
        if movetime_ms is not None:
            self._movetime_ms = movetime_ms
        if depth is not None:
            self._depth = depth
        try:
            self._write(f"position fen {fen}")
            return self._go()
        finally:
            self._movetime_ms, self._depth = previous

    def stop_search(self) -> None:
        if not self._process.is_running():
            return
        try:
            self._write("stop")
        except RuntimeError:
            pass

    def shutdown(self) -> None:
        self._handshook = False
        self._process.stop()

    def _go(self, command: str | None = None) -> tuple[str | None, UciInfo | None]:
        if command is None:
            if self._depth is not None:
                command = f"go depth {self._depth}"
            else:
                command = f"go movetime {self._movetime_ms}"
        self._write(command)
        return self._read_bestmove()

    def _read_bestmove(self) -> tuple[str | None, UciInfo | None]:
        extra = 3.0 if self._depth is not None else 2.0
        deadline = time.monotonic() + self._movetime_ms / 1000 + extra
        if self._depth is not None:
            deadline = time.monotonic() + 12.0
        bestmove: str | None = None
        last_info: UciInfo | None = None
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
                if len(parts) >= 2 and parts[1] != "(none)":
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
