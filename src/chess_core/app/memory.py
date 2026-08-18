"""Memory training: reconstruct position from recall."""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.piece import Piece
from chess_core.core.state import GameState


@dataclass
class MemoryRound:
    target_state: GameState
    reveal_seconds: float


class MemoryTrainingService:
    def start_round(self, state: GameState, reveal_seconds: float) -> MemoryRound:
        if reveal_seconds < 0:
            raise ValueError("reveal_seconds must be non-negative")
        return MemoryRound(target_state=state, reveal_seconds=reveal_seconds)

    def grade_reconstruction(
        self,
        target: GameState,
        attempt: GameState,
    ) -> float:
        if target.board_state.board.shape != attempt.board_state.board.shape:
            raise ValueError("target and attempt board shapes differ")
        cell_count = target.board_state.board.shape.cell_count
        if cell_count == 0:
            return 1.0

        correct = 0
        for square_index in range(cell_count):
            if self._piece_key(target.board_state.cells.get(square_index)) == self._piece_key(
                attempt.board_state.cells.get(square_index)
            ):
                correct += 1

        return correct / cell_count

    def _piece_key(self, piece: Piece | None) -> tuple[str, str] | None:
        if piece is None:
            return None
        return (piece.piece_type.name, piece.side.name)
