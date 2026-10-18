import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox

from chess_core.app.tournament.models import PairingSystem, PlayerStatus
from chess_core.ui.tournament import TournamentWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _select_system(widget: TournamentWidget, system: PairingSystem) -> None:
    index = widget.system.findData(system)
    assert index >= 0
    widget.system.setCurrentIndex(index)


def test_tournament_widget_generates_round_robin_table() -> None:
    _app()
    widget = TournamentWidget()
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    _select_system(widget, PairingSystem.ROUND_ROBIN)
    widget.generate.click()
    assert widget._service is not None
    assert widget.pairings.rowCount() == 2
    assert widget.standings.rowCount() == 4
    widget.close()


def test_tournament_widget_full_swiss_cycle(tmp_path) -> None:
    _app()
    widget = TournamentWidget()
    widget.import_csv_text("name,rating\nАнна,2100\nБорис,2000\nВиктор,1900\nГалина,1800\n")
    widget.generate.click()
    assert widget.pairings.rowCount() == 2
    widget._manager.set_result(1, 1, "1-0")
    widget._manager.set_result(1, 2, "1/2-1/2")
    widget._refresh()
    widget.generate.click()
    assert widget._manager.current_round == 2
    path = widget.save_to(tmp_path / "swiss.json")
    exported = widget.export_xlsx_to(tmp_path / "swiss.xlsx")
    assert path.exists()
    assert exported.exists()
    widget.load_from(path)
    assert widget.standings.rowCount() == 4
    widget.close()


def test_tournament_widget_tabs_round_view_and_result_combo() -> None:
    _app()
    widget = TournamentWidget()
    assert widget.tabs.count() == 5
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    _select_system(widget, PairingSystem.ROUND_ROBIN)
    widget.generate.click()
    assert widget.tabs.currentIndex() == 1
    assert isinstance(widget.pairings.cellWidget(0, 3), QComboBox)
    widget.close()


def test_tournament_widget_half_bye_restore_and_crosstable() -> None:
    _app()
    widget = TournamentWidget()
    widget.import_csv_text("name,rating\nАнна,2100\nБорис,2000\nВиктор,1900\nГалина,1800\n")
    widget.players_table.selectRow(0)
    player_id = widget._selected_player_id()
    assert player_id
    widget.bye_button.click()
    widget.generate.click()
    names = [
        widget.pairings.item(row, 2).text()
        for row in range(widget.pairings.rowCount())
    ]
    assert "BYE" in names
    widget._manager.set_player_status(player_id, PlayerStatus.WITHDRAWN)
    widget._manager.set_player_status(player_id, PlayerStatus.ACTIVE)
    widget._refresh()
    assert widget._manager.state.player_map()[player_id].status is PlayerStatus.ACTIVE
    assert widget.crosstable.rowCount() == 4
    widget.close()


def test_tournament_widget_result_arrows_keep_combo_focus() -> None:
    _app()
    widget = TournamentWidget()
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    _select_system(widget, PairingSystem.ROUND_ROBIN)
    widget.generate.click()
    first = widget.pairings.cellWidget(0, 3)
    second = widget.pairings.cellWidget(1, 3)
    assert isinstance(first, QComboBox)
    assert isinstance(second, QComboBox)
    widget.show()
    first.setFocus()
    first.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))
    assert widget.pairings.currentRow() == 1
    second.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier))
    assert widget.pairings.currentRow() == 0
    QTest.keyClick(first, Qt.Key.Key_1)
    assert widget._manager.round_pairings(1)[0].result == "1-0"
    assert widget.pairings.cellWidget(0, 3) is first
    assert widget.pairings.currentRow() == 1
    widget.close()


def test_tournament_widget_starting_list_follows_rating() -> None:
    _app()
    widget = TournamentWidget()
    widget.import_csv_text("name,rating\nLow,1400\nHigh,2200\nMid,1800\nNia,1700\n")
    assert widget.players_table.item(0, 2).text() == "High"
    assert widget.players_table.item(0, 0).text() == "1"
    assert widget.players_table.item(0, 4).text() == "2200"
    widget.sort_rating_button.click()
    assert widget.players_table.item(1, 2).text() == "Mid"
    widget.close()


def test_tournament_widget_swiss_no_color_labels() -> None:
    _app()
    widget = TournamentWidget()
    _select_system(widget, PairingSystem.SWISS_NO_COLOR)
    assert widget.invert_button.text() == "Места"
    assert widget.pairings.horizontalHeaderItem(1).text() == "Игрок 1"
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    widget.generate.click()
    assert widget._manager.state.settings.system is PairingSystem.SWISS_NO_COLOR
    assert widget.pairings.rowCount() == 2
    widget.close()


def test_tournament_widget_player_selection_clear_and_middle_click_add() -> None:
    _app()
    widget = TournamentWidget()
    widget.import_csv_text("name,rating\nАнна,2100\nБорис,2000\n")
    widget.players_table.selectRow(0)
    assert widget._selected_player_id() is not None
    widget._clear_player_selection()
    assert widget._selected_player_id() is None

    widget.players_table.selectRow(0)
    viewport = widget.players_table.viewport()
    widget.players_table.resize(400, 320)
    empty = QPointF(10, 300)
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        empty,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.eventFilter(viewport, press)
    assert widget._selected_player_id() is None

    middle = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        empty,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert widget.eventFilter(viewport, middle) is True
    assert widget._player_draft is True
    assert widget._draft_row() == 2
    widget.close()


def test_tournament_widget_player_entry_chains_then_empty_click_stops() -> None:
    _app()
    widget = TournamentWidget()
    widget._begin_player_entry()
    assert widget._player_draft is True
    draft = widget._draft_row()
    assert draft == 0
    widget.players_table.item(draft, 2).setText("Анна")
    widget._on_player_cell_changed(draft, 2)
    assert any(player.name == "Анна" for player in widget._manager.players)
    assert widget._player_draft is True
    second = widget._draft_row()
    assert second is not None
    assert widget.players_table.item(second, 2).text() == ""

    widget._stop_player_chain = True
    widget._clear_player_selection()
    assert widget._player_draft is False
    assert widget._draft_row() is None
    assert [player.name for player in widget._manager.players] == ["Анна"]
    widget.close()


def test_tournament_widget_double_click_opens_player_editor(monkeypatch) -> None:
    _app()
    widget = TournamentWidget()
    widget.import_csv_text("name,rating\nАнна,2100\nБорис,2000\n")
    opened: list[str] = []

    class _FakeDialog:
        DialogCode = type("C", (), {"Accepted": 1})()

        def __init__(self, parent=None, player=None) -> None:
            del parent
            opened.append(player.name if player is not None else "")

        def exec(self) -> int:
            return 0

    monkeypatch.setattr("chess_core.ui.tournament.PlayerDialog", _FakeDialog)
    assert widget._edit_player_at_row(1) is True
    assert opened == ["Борис"]
    widget.close()


def test_tournament_widget_delete_round_keeps_players_and_unlocks_system() -> None:
    _app()
    widget = TournamentWidget()
    _select_system(widget, PairingSystem.SWISS_NO_COLOR)
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    widget.generate.click()
    assert widget.system.isEnabled() is False
    names = [player.name for player in widget._manager.players]
    widget._manager.delete_rounds_from(1, reason="тест")
    widget._refresh()
    assert widget._manager.current_round == 0
    assert widget.system.isEnabled() is True
    assert [player.name for player in widget._manager.players] == names
    widget.close()
