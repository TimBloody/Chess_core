"""USI protocol client (shogi engines)."""

from __future__ import annotations

from chess_core.infra.engines.uci import UciClient, UciInfo


class UsiClient(UciClient):
    def __init__(
        self,
        executable: str,
        *,
        movetime_ms: int = 500,
        depth: int | None = None,
        options: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            executable,
            movetime_ms=movetime_ms,
            depth=depth,
            options=options,
        )
        self._hello = "usi"
        self._hello_token = "usiok"
        self._newgame = "usinewgame"
        self._ready_timeout = 20.0

    def analyze_sfen(
        self,
        sfen: str,
        *,
        movetime_ms: int | None = None,
        depth: int | None = None,
    ) -> tuple[str | None, UciInfo | None]:
        del depth
        self.handshake()
        previous = self._movetime_ms
        if movetime_ms is not None:
            self._movetime_ms = movetime_ms
        try:
            self._write(f"position sfen {sfen}")
            return self._go(f"go byoyomi {self._movetime_ms}")
        finally:
            self._movetime_ms = previous
