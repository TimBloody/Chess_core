"""Single-player checkbox plays an engine reply."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chess_core.app.engine import SearchLimit
from chess_core.core.notation import parse_uci
from chess_core.core.piece import PieceSide
from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.local_game import LocalGameWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_vs_computer_checkbox_engine_replies() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget._play_limit = SearchLimit(depth=1, movetime_ms=1200)
    widget._engine_move_delay_ms = 0
    assert widget.vs_computer.isEnabled()
    widget.vs_computer.setChecked(True)
    widget.service.play(parse_uci("e2e4"))
    widget._refresh()
    for _ in range(40):
        QApplication.processEvents()
        QTest.qWait(50)
        if widget.service.record.live_revision >= 2:
            break
    assert widget.service.record.live_revision >= 2
    assert widget.service.state.side_to_move is PieceSide.WHITE
    after_reply = widget.service.record.live_revision
    QTest.qWait(200)
    QApplication.processEvents()
    assert widget.service.record.live_revision == after_reply
    widget.close()


def test_engine_move_previews_before_commit() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget._play_limit = SearchLimit(depth=1, movetime_ms=1200)
    widget._engine_move_delay_ms = 10_000
    widget.vs_computer.setChecked(True)
    widget.service.play(parse_uci("e2e4"))
    widget._refresh()
    for _ in range(40):
        QApplication.processEvents()
        QTest.qWait(50)
        if widget._pending_engine_turn is not None:
            break
    assert widget._pending_engine_turn is not None
    assert widget._engine_preview is not None
    assert widget.service.record.live_revision == 1
    widget._commit_pending_engine_turn()
    assert widget.service.record.live_revision >= 2
    widget.close()


def test_vs_computer_does_not_search_on_human_turn() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget.enable_engine_analysis(True)
    widget.vs_computer.setChecked(True)
    bridge = widget._engine_bridge
    assert bridge is not None
    purposes: list[str] = []
    real = bridge.request_analysis

    def spy(request) -> None:
        purposes.append(request.purpose)
        real(request)

    bridge.request_analysis = spy  # type: ignore[method-assign]
    widget._request_engine()
    assert purposes == []
    widget.service.play(parse_uci("e2e4"))
    widget._request_engine()
    assert purposes == ["play"]
    widget.close()


def test_two_player_hints_and_eval_are_opt_in() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    assert widget.evaluation_bar.isHidden()
    assert not widget.show_eval.isChecked()
    assert widget._engine_bridge is None
    assert not hasattr(widget, "engine_name")
    assert widget._hints_shortcut.key().toString() == "H"
    assert widget._eval_shortcut.key().toString() == "G"

    widget._toggle_hints()
    assert widget._hints_enabled
    assert widget._engine_bridge is not None

    widget.show_eval.setChecked(True)
    assert not widget.evaluation_bar.isHidden()
    widget.show_eval.setChecked(False)
    assert widget.evaluation_bar.isHidden()
    widget.close()


def test_vs_computer_hidden_for_bughouse() -> None:
    _app()
    register_builtin_modes()
    widget = LocalGameWidget(default_registry.get, "bughouse", discovered=[])
    assert widget.vs_computer.isEnabled() is False
    assert "две доски" in widget.status.text()
    widget.close()


def test_duck_fairy_overlay_rebuilds_compatible_mode() -> None:
    from chess_core.modes import resolve_mode
    from chess_core.ui.mode_picker import ModePicker, UiSession

    _app()
    register_builtin_modes()
    session = UiSession("duck")
    picker = ModePicker(default_registry.list_modes(), session)
    widget = LocalGameWidget(resolve_mode, "duck", discovered=[])
    assert widget.service.mode.checks_enabled
    picker._checkboxes["fairy"].setChecked(True)
    widget.set_mode(session.mode_id)
    assert session.mode_id == "chess+duck+fairy"
    assert not widget.service.mode.checks_enabled
    assert widget.service.mode.initial_extras["fairy_duck_rules"] is True
    assert "взятием" in widget.instructions.text()
    picker._checkboxes["fairy"].setChecked(False)
    widget.set_mode(session.mode_id)
    assert session.mode_id == "duck"
    assert widget.service.mode.checks_enabled
    assert "шахи" in widget.instructions.text()
    widget.close()
    picker.close()
