"""Local play branch: over-the-board game plus board editor."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from chess_core.core.gamemode import GameMode
from chess_core.modes import resolve_mode
from chess_core.ui.branches._modes import prepared_mode_ids
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.shell import BranchWindow, PageSpec


class LocalPlayWindow(BranchWindow):
    def __init__(
        self,
        mode_ids: Iterable[str] | None = None,
        session: UiSession | None = None,
        mode_resolver: Callable[[str], GameMode] = resolve_mode,
        parent=None,
    ) -> None:
        ids, session = prepared_mode_ids(session)
        if mode_ids is not None:
            ids = list(mode_ids)
        self._resolve = mode_resolver
        super().__init__(
            "Chess Core — Локальная игра",
            (
                PageSpec("Локальная игра", self._make_local_game, follows_mode=True),
                PageSpec("Редактор", self._make_editor, follows_mode=True),
            ),
            mode_ids=ids,
            session=session,
            show_mode_picker=True,
            parent=parent,
        )

    @property
    def _local_game(self):
        return self.page_widget("Локальная игра")

    @property
    def _editor(self):
        return self.page_widget("Редактор")

    def _make_local_game(self):
        from chess_core.ui.local_game import LocalGameWidget

        mode_id = self.session.mode_id or "chess"
        return LocalGameWidget(self._resolve, mode_id)

    def _make_editor(self):
        from chess_core.ui.editor import EditorWidget

        mode_id = self.session.mode_id or "chess"
        editor = EditorWidget(self._resolve, mode_id)
        editor.play_requested.connect(self._start_from_editor)
        return editor

    def _start_from_editor(self, state: object) -> None:
        game = self._local_game
        game.load_position(state)
        self.show_page_title("Локальная игра")
