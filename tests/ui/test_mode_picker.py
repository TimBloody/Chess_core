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


def test_corners_checkboxes_are_exclusive() -> None:
    _app()
    session = UiSession("corners")
    picker = ModePicker(["chess", "corners"], session)
    picker.show()
    assert session.mode_id == "corners"
    assert picker._corners_panel.isVisible()
    assert picker._corner_boxes["3x4"].isChecked()
    assert not picker._corner_boxes["3x3"].isChecked()

    picker._corner_boxes["3x3"].setChecked(True)
    assert session.mode_id == "corners+3x3"
    assert picker._corner_boxes["3x3"].isChecked()
    assert not picker._corner_boxes["3x4"].isChecked()

    picker._corner_boxes["1234"].setChecked(True)
    assert session.mode_id == "corners+1234"

    picker._combo.setCurrentIndex(0)
    assert session.mode_id == "chess"
    assert not picker._corners_panel.isVisible()
    picker.close()


def test_session_restores_corners_layout() -> None:
    _app()
    session = UiSession("corners+1234")
    picker = ModePicker(["chess", "corners"], session)
    assert session.mode_id == "corners+1234"
    assert picker._corner_boxes["1234"].isChecked()
    assert not picker._corner_boxes["3x4"].isChecked()
    picker.close()


def test_checkers_checkboxes_compose_mode_id() -> None:
    _app()
    session = UiSession("checkers")
    picker = ModePicker(["chess", "checkers"], session)
    picker.show()
    assert session.mode_id == "checkers"
    assert picker._checkers_panel.isVisible()
    picker._checker_boxes["flying_king"].setChecked(False)
    assert session.mode_id == "checkers+mandatory_capture+backward_capture"
    picker.close()


def test_gobblet_relocate_checkbox_composes_mode_id() -> None:
    _app()
    session = UiSession("gobblet")
    picker = ModePicker(["chess", "gobblet"], session)
    picker.show()
    assert session.mode_id == "gobblet"
    assert picker._gobblet_panel.isVisible()
    assert not picker._gobblet_relocate.isChecked()

    picker._gobblet_relocate.setChecked(True)
    assert session.mode_id == "gobblet+relocate"

    picker._combo.setCurrentIndex(0)
    assert session.mode_id == "chess"
    assert not picker._gobblet_panel.isVisible()
    picker.close()


def test_session_restores_gobblet_relocate() -> None:
    _app()
    session = UiSession("gobblet+relocate")
    picker = ModePicker(["chess", "gobblet"], session)
    assert session.mode_id == "gobblet+relocate"
    assert picker._gobblet_relocate.isChecked()
    picker.close()
