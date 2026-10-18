"""Tournament manager dialogs."""

from chess_core.ui.widgets.tournament.pairing_edit import PairingEditDialog
from chess_core.ui.widgets.tournament.result_combo import ResultCombo
from chess_core.ui.widgets.tournament.player_dialog import (
    GoogleSheetDialog,
    PlayerDialog,
    TournamentPropertiesDialog,
)

__all__ = [
    "GoogleSheetDialog",
    "PairingEditDialog",
    "PlayerDialog",
    "ResultCombo",
    "TournamentPropertiesDialog",
]
