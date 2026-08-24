import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.ui.tournament import TournamentWidget

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_tournament_widget_generates_round_robin_table() -> None:
    _app()
    widget = TournamentWidget()
    widget.players_edit.setPlainText("Анна\nБорис\nВиктор\nГалина")
    widget.generate.click()
    assert widget._service is not None
    assert widget.pairings.rowCount() == 6
    assert widget.standings.rowCount() == 4
    widget.close()
