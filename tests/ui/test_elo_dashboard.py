import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chess_core.ui.experiments import EloDashboard


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_dashboard_builds_and_reacts_to_parameters() -> None:
    app = _app()
    dashboard = EloDashboard()
    assert dashboard.table.rowCount() == 10
    assert "99.0%" in dashboard.gap_card.value.text()
    original_leader = dashboard.leader_card.value.text()

    dashboard.seed.setValue(99)
    dashboard._refresh()
    app.processEvents()

    assert dashboard.leader_card.value.text()
    assert dashboard.pool_card.value.text().startswith("50 игроков")
    assert dashboard.trajectory_plot.listDataItems()
    assert dashboard.probability_plot.listDataItems()
    assert original_leader or dashboard.leader_card.value.text()
    dashboard.close()
