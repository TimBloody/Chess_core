import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.core.registry import default_registry
from chess_core.core.rules import VictoryKind
from chess_core.modes import register_builtin_modes, resolve_mode
from chess_core.modes.giveaway_rules import MustCaptureLegality
from chess_core.ui.branches.local_play import LocalPlayWindow
from chess_core.ui.branches.server_play import ServerPlayWindow
from chess_core.ui.mode_picker import ModePicker, UiSession


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _checkboxes(picker: ModePicker) -> dict:
    return picker._checkboxes


def test_local_and_network_pickers_combine_giveaway_and_fairy() -> None:
    _app()
    register_builtin_modes()
    ids = default_registry.list_modes()

    local = LocalPlayWindow(ids, UiSession("chess"))
    picker = local._picker
    boxes = _checkboxes(picker)
    assert not boxes["giveaway"].isHidden()
    assert not boxes["fairy"].isHidden()
    boxes["giveaway"].setChecked(True)
    boxes["fairy"].setChecked(True)
    assert local.session.mode_id == "chess+fairy+giveaway"
    mode = local._local_game.service.mode
    assert isinstance(mode.legality, MustCaptureLegality)
    kinds = {item.kind for item in (mode.victory if isinstance(mode.victory, tuple) else (mode.victory,))}
    assert VictoryKind.MATERIAL in kinds
    assert mode.initial_extras.get("fairy_rules") is True
    assert mode.move_resolver is not None
    local.close()

    network = ServerPlayWindow(ids, UiSession("chess"))
    net_boxes = _checkboxes(network._picker)
    assert not net_boxes["giveaway"].isHidden()
    net_boxes["giveaway"].setChecked(True)
    net_boxes["fairy"].setChecked(True)
    assert network.session.mode_id == "chess+fairy+giveaway"
    assert network._network_game._mode_id == "chess+fairy+giveaway"
    network.close()


def test_mode_picker_hides_chess_overlays_on_shogi() -> None:
    _app()
    register_builtin_modes()
    session = UiSession("chess")
    picker = ModePicker(default_registry.list_modes(), session)
    family = picker._family_combo.findData("shogi")
    picker._family_combo.setCurrentIndex(family)
    index = picker._combo.findData("shogi")
    picker._combo.setCurrentIndex(index)
    assert picker._checkboxes["giveaway"].isHidden()
    assert picker._checkboxes["fairy"].isHidden()
    assert session.mode_id == "shogi"
    picker.close()


def test_mode_picker_families_expose_hasami_and_nanai() -> None:
    _app()
    register_builtin_modes()
    session = UiSession("chess")
    picker = ModePicker(default_registry.list_modes(), session)

    picker._family_combo.setCurrentIndex(picker._family_combo.findData("shogi"))
    assert picker._combo.findData("hasami_shogi") >= 0
    picker._combo.setCurrentIndex(picker._combo.findData("hasami_shogi"))
    assert session.mode_id == "hasami_shogi"
    assert picker._overlays_title.isHidden()

    picker._family_combo.setCurrentIndex(picker._family_combo.findData("board"))
    assert picker._combo.findData("nanai_checkers") >= 0
    picker._combo.setCurrentIndex(picker._combo.findData("nanai_checkers"))
    assert session.mode_id == "nanai_checkers"
    picker.close()


def test_resolve_mode_builds_unregistered_composite() -> None:
    mode = resolve_mode("chess+fairy+giveaway")
    assert mode.id == "chess+fairy+giveaway"
    assert isinstance(mode.legality, MustCaptureLegality)
    assert mode.move_resolver is not None


def test_local_and_network_fairytale_alone_has_file_resolver() -> None:
    _app()
    register_builtin_modes()
    ids = default_registry.list_modes()

    local = LocalPlayWindow(ids, UiSession("chess"))
    _checkboxes(local._picker)["fairy"].setChecked(True)
    assert local.session.mode_id == "fairy"
    assert local._local_game.service.mode.move_resolver is not None
    local.close()

    network = ServerPlayWindow(ids, UiSession("chess"))
    _checkboxes(network._picker)["fairy"].setChecked(True)
    assert network.session.mode_id == "fairy"
    assert network._network_game._mode_id == "fairy"
    assert resolve_mode(network._network_game._mode_id).move_resolver is not None
    network.close()


def test_branch_window_fullscreen_button_toggles() -> None:
    _app()
    register_builtin_modes()
    window = LocalPlayWindow(["chess"], UiSession("chess"))
    window.show()
    assert not window.isFullScreen()
    assert not window.fullscreen_button.isChecked()
    window.fullscreen_button.click()
    assert window.isFullScreen()
    assert window.fullscreen_button.isChecked()
    window.fullscreen_button.click()
    assert not window.isFullScreen()
    assert not window.fullscreen_button.isChecked()
    window.close()
