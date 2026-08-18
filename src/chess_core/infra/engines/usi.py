"""USI protocol client (shogi engines)."""

from __future__ import annotations

from chess_core.infra.engines.uci import UciClient, UciInfo


class UsiClient(UciClient):
    def handshake(self) -> None:
        self._process.start()
        self._write("usi")
        self._wait_for("usiok", timeout=5.0)
        self._write("isready")
        self._wait_for("readyok", timeout=5.0)

    def analyze_sfen(self, sfen: str) -> tuple[str | None, UciInfo | None]:
        self._write(f"position sfen {sfen}")
        self._write(f"go btime {self._movetime_ms}")
        return self.analyze_fen(sfen)
