"""Education branch: puzzles, memory, board setup, PGN/ChessBase, piece mazes."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from chess_core.core.gamemode import GameMode
from chess_core.modes import resolve_mode
from chess_core.ui.branches._modes import prepared_mode_ids
from chess_core.ui.mode_picker import UiSession
from chess_core.ui.shell import BranchWindow, PageSpec


class EducationWindow(BranchWindow):
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
            "Chess Core — Обучение",
            (
                PageSpec("Задачи", self._make_puzzles),
                PageSpec("По памяти", self._make_memory, follows_mode=True),
                PageSpec("Редактор", self._make_editor, follows_mode=True),
                PageSpec("Анализ", self._make_analysis, follows_mode=True),
                PageSpec("Базы", self._make_database),
                PageSpec("Лабиринт", self._make_maze),
            ),
            mode_ids=ids,
            session=session,
            show_mode_picker=True,
            parent=parent,
        )

    @property
    def _puzzles(self):
        return self.page_widget("Задачи")

    @property
    def _memory(self):
        return self.page_widget("По памяти")

    @property
    def _editor(self):
        return self.page_widget("Редактор")

    @property
    def _pgn_analysis(self):
        return self.page_widget("Анализ")

    @property
    def _pgn_database(self):
        return self.page_widget("Базы")

    @property
    def _maze(self):
        return self.page_widget("Лабиринт")

    def _make_puzzles(self):
        from chess_core.ui.puzzles import PuzzleWidget

        return PuzzleWidget()

    def _make_memory(self):
        from chess_core.ui.training.memory_widget import MemoryTrainingWidget

        mode_id = self.session.mode_id or "chess"
        return MemoryTrainingWidget(self._resolve, mode_id)

    def _make_editor(self):
        from chess_core.ui.editor import EditorWidget

        mode_id = self.session.mode_id or "chess"
        editor = EditorWidget(
            self._resolve,
            mode_id,
            play_button_text="Анализировать позицию",
        )
        editor.play_button.setToolTip(
            "Открыть позицию на вкладке «Анализ»: можно ходить по правилам и смотреть оценку."
        )
        editor.play_requested.connect(self._analyse_from_editor)
        return editor

    def _analyse_from_editor(self, state: object) -> None:
        analysis = self.show_page_title("Анализ")
        analysis.load_position(state)

    def _make_analysis(self):
        from chess_core.ui.pgn_analysis import PgnAnalysisWidget

        mode_id = self.session.mode_id or "chess"
        return PgnAnalysisWidget(self._resolve, mode_id)

    def _make_database(self):
        from chess_core.ui.pgn_database import PgnDatabaseWidget

        return PgnDatabaseWidget()

    def _make_maze(self):
        from chess_core.ui.training.maze_widget import MazeTrainingWidget

        return MazeTrainingWidget()
