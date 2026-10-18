"""Tournament branch: pairings manager only."""

from __future__ import annotations

from chess_core.ui.shell import BranchWindow, PageSpec


class TournamentWindow(BranchWindow):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Chess Core — Турнир",
            (PageSpec("Жеребьёвка", self._make_tournament),),
            show_mode_picker=False,
            parent=parent,
        )

    def _make_tournament(self):
        from chess_core.ui.tournament import TournamentWidget

        return TournamentWidget()
