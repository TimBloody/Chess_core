import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.modes import register_builtin_modes
from chess_core.ui.mode_picker import ModePicker, UiSession

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_mode_picker_checkbox_changes_session_mode_id() -> None:
    _app()
    register_builtin_modes()
    session = UiSession("chess")
    picker = ModePicker(default_registry.list_modes(), session)

    assert session.mode_id == "chess"
    picker._modifier_boxes["cylindrical"].setChecked(True)
    assert session.mode_id == "cylindrical"

    picker._modifier_boxes["three_check"].setChecked(True)
    assert session.mode_id == "chess+cylindrical+three_check"

    picker._combo.setCurrentIndex(picker._mode_ids.index("shogi"))
    assert not picker._modifier_panel.isVisible()
    assert session.mode_id == "shogi"

    picker.close()
