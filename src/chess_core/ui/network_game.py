"""LAN host/join page: authoritative server on the host, guest over TCP."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from chess_core.app.network_game import (
    GuestTurnTransport,
    HostTurnTransport,
    NetworkedLocalGameService,
)
from chess_core.core.gamemode import GameMode
from chess_core.core.piece import PieceSide
from chess_core.core.time_control import TimeControlConfig, TimeControlKind
from chess_core.infra.lan import lan_ipv4_addresses
from chess_core.infra.network import GameServer
from chess_core.infra.network_messages import (
    DEFAULT_GAME_PORT,
    HelloOkPayload,
    OpponentLeft,
    StateEnvelope,
    TurnRejectedPayload,
    UndoPending,
    UndoResolved,
)
from chess_core.infra.clock_sync import ClockProjection
from chess_core.infra.tcp_client import HelloRejectedError, TcpGameClient
from chess_core.infra.tcp_server import TcpGameServer
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.theme import mode_display_name


class _AsyncLoopThread(QThread):
    def __init__(self) -> None:
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()

    def run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()
        self.loop.close()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout):
            raise RuntimeError("network event loop failed to start")

    def stop(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)


class NetworkSignals(QObject):
    """Queued cross-thread notifications for the network page."""

    message = pyqtSignal(object)
    peer_ready = pyqtSignal()
    error = pyqtSignal(str)


class NetworkBoardWidget(LocalGameWidget):
    undo_requested = pyqtSignal()

    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            mode_resolver,
            mode_id,
            parent,
            allow_temporary_variations=False,
        )
        self.new_game_button.hide()
        self.mainline_button.hide()
        self.hint_button.hide()
        self.quit_button.hide()
        self._reset_shortcut.setEnabled(False)
        self.instructions.setText(
            "Сетевая партия: ходы применяет сервер хоста. "
            "Чужие фигуры и ход соперника недоступны. Ctrl+Z — запрос отмены."
        )
        self._clock_projection = ClockProjection()

    def undo_move(self) -> None:
        service = self._service
        if service is None:
            return
        if service.pending_actions:
            super().undo_move()
            return
        self.undo_requested.emit()

    def _tick_clock_display(self) -> None:
        service = self._service
        if not isinstance(service, NetworkedLocalGameService):
            super()._tick_clock_display()
            return
        snapshot = service.clock_snapshot
        now = int(time.monotonic() * 1000)
        if snapshot is not None:
            if (
                self._clock_projection._snapshot is None
                or self._clock_projection.revision != snapshot.revision
            ):
                self._clock_projection.apply_snapshot(snapshot, client_mono_ms=now)
        self.white_clock.apply_snapshot(snapshot, client_mono_ms=now)
        self.black_clock.apply_snapshot(snapshot, client_mono_ms=now)
        if snapshot is None:
            self.clock_mode.setText("")
            return
        self.clock_mode.setText(
            {
                TimeControlKind.SIMPLE: "Sudden death",
                TimeControlKind.FISCHER: "Fischer",
                TimeControlKind.BRONSTEIN: "Bronstein",
                TimeControlKind.BYOYOMI: "Byoyomi",
            }[snapshot.time_control.kind]
        )

    def _refresh(self) -> None:
        super()._refresh()
        service = self._service
        if isinstance(service, NetworkedLocalGameService) and not service.match_ready:
            self.status.setText("Ждём соперника…")
        elif isinstance(service, NetworkedLocalGameService) and service.pending_undo is not None:
            if service.pending_undo.requester_side is service.assigned_side:
                self.status.setText("Запрос отмены отправлен. Ждём ответа соперника.")


class NetworkGameWidget(QWidget):
    def __init__(
        self,
        mode_resolver: Callable[[str], GameMode],
        mode_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resolve = mode_resolver
        self._mode_id = mode_id
        self._thread: _AsyncLoopThread | None = None
        self._tcp_server: TcpGameServer | None = None
        self._tcp_client: TcpGameClient | None = None
        self._game_server: GameServer | None = None
        self._host_session_id: str | None = None
        self._active = False
        self._signals = NetworkSignals(self)
        self._signals.message.connect(self._on_network_message)
        self._signals.peer_ready.connect(self._on_peer_ready)
        self._signals.error.connect(self._on_network_error)

        self.status = QLabel("Выберите режим слева, затем создайте партию или подключитесь.")
        self.status.setWordWrap(True)
        self.lan_label = QLabel(_lan_text())
        self.lan_label.setWordWrap(True)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(DEFAULT_GAME_PORT)
        self.host_input = QLineEdit("127.0.0.1")
        self.host_button = QPushButton("Создать партию")
        self.join_button = QPushButton("Подключиться")
        self.disconnect_button = QPushButton("Отключиться")
        self.disconnect_button.setEnabled(False)
        self.host_button.clicked.connect(self._host_game)
        self.join_button.clicked.connect(self._join_game)
        self.disconnect_button.clicked.connect(self.disconnect)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Порт"))
        controls.addWidget(self.port_input)
        controls.addWidget(self.host_button)
        controls.addWidget(QLabel("IP хоста"))
        controls.addWidget(self.host_input, 1)
        controls.addWidget(self.join_button)
        controls.addWidget(self.disconnect_button)

        self.board = NetworkBoardWidget(mode_resolver, mode_id)
        self.board.undo_requested.connect(self._request_undo)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.lan_label)
        layout.addLayout(controls)
        layout.addWidget(self.board, 1)

    def set_mode(self, mode_id: str) -> None:
        self._mode_id = mode_id
        if self._active:
            return
        self.board.set_mode(mode_id)

    def reload_piece_assets(self) -> None:
        self.board.reload_piece_assets()

    def disconnect(self) -> None:
        thread = self._thread
        tcp_server = self._tcp_server
        tcp_client = self._tcp_client
        self._tcp_server = None
        self._tcp_client = None
        self._game_server = None
        self._host_session_id = None
        self._active = False
        if thread is not None and tcp_server is not None:
            try:
                asyncio.run_coroutine_threadsafe(tcp_server.close(), thread.loop).result(3)
            except Exception:
                pass
        if thread is not None and tcp_client is not None:
            try:
                asyncio.run_coroutine_threadsafe(tcp_client.close(), thread.loop).result(3)
            except Exception:
                pass
        if thread is not None:
            thread.stop()
            thread.wait(3000)
        self._thread = None
        self.host_button.setEnabled(True)
        self.join_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_input.setEnabled(True)
        self.host_input.setEnabled(True)
        self.board.set_mode(self._mode_id)
        self.status.setText("Отключено.")

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self.disconnect()
        super().closeEvent(event)

    def _host_game(self) -> None:
        if self._active:
            return
        mode = self._resolve(self._mode_id)
        try:
            thread = self._start_loop()
            server = GameServer(
                mode.initial_state(),
                mode=mode,
                time_control=TimeControlConfig.blitz(),
            )
            host_session = server.connect_client()
            tcp = TcpGameServer(
                server,
                port=int(self.port_input.value()),
                on_remote_event=lambda _session: self._signals.peer_ready.emit(),
            )
            server.add_observer(self._on_host_server_message)
            port = asyncio.run_coroutine_threadsafe(tcp.start(), thread.loop).result(5)
        except Exception as exc:
            self.disconnect()
            self.status.setText(f"Не удалось открыть порт: {exc}")
            return
        self._thread = thread
        self._game_server = server
        self._tcp_server = tcp
        self._host_session_id = host_session.session_id
        self._active = True
        service = NetworkedLocalGameService(
            mode,
            assigned_side=host_session.side,
            transport=HostTurnTransport(server, host_session.session_id),
            match_ready=False,
        )
        self.board.attach_service(
            service,
            mode_id=self._mode_id,
            view_side=host_session.side,
        )
        self._lock_connection_controls()
        addresses = ", ".join(lan_ipv4_addresses()) or "IP локальной сети не найден"
        self.status.setText(
            f"Партия {mode_display_name(self._mode_id)}. "
            f"Слушаем порт {port}. Адреса: {addresses}. Ждём соперника."
        )

    def _join_game(self) -> None:
        if self._active:
            return
        host = self.host_input.text().strip()
        port = int(self.port_input.value())
        if not host:
            self.status.setText("Укажите IP хоста.")
            return
        try:
            thread = self._start_loop()
            client = TcpGameClient(self._signals.message.emit)
            hello = asyncio.run_coroutine_threadsafe(
                client.connect(host, port),
                thread.loop,
            ).result(8)
        except HelloRejectedError as exc:
            self.disconnect()
            self.status.setText(_reject_text(exc.reason))
            return
        except Exception as exc:
            self.disconnect()
            self.status.setText(f"Не удалось подключиться: {exc}")
            return
        self._thread = thread
        self._tcp_client = client
        self._active = True
        self._lock_connection_controls()
        self._attach_guest(hello)

    def _attach_guest(self, hello: HelloOkPayload) -> None:
        mode = self._resolve(hello.mode_id)
        assert self._tcp_client is not None
        service = NetworkedLocalGameService(
            mode,
            assigned_side=hello.side,
            transport=GuestTurnTransport(self._tcp_client),
            match_ready=True,
        )
        self._mode_id = hello.mode_id
        self.board.attach_service(
            service,
            mode_id=hello.mode_id,
            view_side=hello.side,
        )
        color = "белыми" if hello.side is PieceSide.WHITE else "чёрными"
        self.status.setText(
            f"Подключено к {mode_display_name(hello.mode_id)}. Вы играете {color}."
        )

    def _on_host_server_message(self, session_id: str, message: object) -> None:
        if session_id != self._host_session_id:
            return
        self._signals.message.emit(message)

    def _on_peer_ready(self) -> None:
        service = self.board._service
        if isinstance(service, NetworkedLocalGameService):
            service.set_match_ready(True)
        self.status.setText("Соперник подключился. Можно ходить.")
        self.board._refresh()

    def _on_network_message(self, message: object) -> None:
        if isinstance(message, HelloOkPayload):
            if self.board._service is None or not isinstance(
                self.board._service, NetworkedLocalGameService
            ):
                self._attach_guest(message)
            return
        if isinstance(message, TurnRejectedPayload):
            self.status.setText(f"Ход отклонён: {message.reason}")
            return
        if isinstance(message, OpponentLeft):
            self.status.setText("Соперник отключился.")
            service = self.board._service
            if isinstance(service, NetworkedLocalGameService):
                service.set_match_ready(False)
            self.board._refresh()
            return
        if isinstance(message, UndoPending):
            self._handle_undo_pending(message)
            return
        service = self.board._service
        if isinstance(service, NetworkedLocalGameService):
            service.apply_server_message(message)
            if isinstance(message, UndoResolved) and not message.accepted:
                self.status.setText("Соперник отклонил отмену хода.")
        self.board._refresh()

    def _handle_undo_pending(self, pending: UndoPending) -> None:
        service = self.board._service
        if not isinstance(service, NetworkedLocalGameService):
            return
        service.apply_server_message(pending)
        self.board._refresh()
        if pending.requester_side is service.assigned_side:
            return
        answer = QMessageBox.question(
            self,
            "Отмена хода",
            "Соперник просит взять ход назад. Согласиться?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        try:
            service.respond_undo(answer == QMessageBox.StandardButton.Yes)
        except Exception as exc:
            self.status.setText(f"Не удалось ответить на отмену: {exc}")

    def _request_undo(self) -> None:
        service = self.board._service
        if not isinstance(service, NetworkedLocalGameService):
            return
        try:
            service.undo()
        except Exception as exc:
            self.status.setText(f"Нельзя запросить отмену: {exc}")
            return
        self.board._refresh()

    def _on_network_error(self, text: str) -> None:
        self.status.setText(text)

    def _start_loop(self) -> _AsyncLoopThread:
        thread = _AsyncLoopThread()
        thread.start()
        thread.wait_ready()
        self._thread = thread
        return thread

    def _lock_connection_controls(self) -> None:
        self.host_button.setEnabled(False)
        self.join_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.port_input.setEnabled(False)
        self.host_input.setEnabled(False)


def _lan_text() -> str:
    addresses = lan_ipv4_addresses()
    if not addresses:
        return "Локальный IP не найден — соперник может подключиться по адресу из ipconfig."
    return "Ваши адреса в LAN: " + ", ".join(addresses)


def _reject_text(reason: str) -> str:
    return {
        "version_mismatch": "Разные версии клиента. Установите одинаковую сборку.",
        "protocol_mismatch": "Несовместимый сетевой протокол.",
        "game_full": "В партии уже два игрока.",
        "bad_hello": "Сервер отклонил подключение.",
    }.get(reason, f"Сервер отклонил подключение: {reason}")
