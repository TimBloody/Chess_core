"""Configurable move generation for 8x8 checkers.

Default options match a hybrid of Russian and international draughts:
mandatory maximum capture, men capture backwards, flying kings, and a man
that reaches the last rank during a capture continues as a king on the same
turn. Captured pieces stay as obstacles until the whole sequence ends and
cannot be jumped twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from chess_core.core.board import Square
from chess_core.core.move import Action, MoveAction
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import GameState


MAN = PieceTypeId("checker_man")
KING = PieceTypeId("checker_king")
DIAGONALS = ((-1, -1), (1, -1), (-1, 1), (1, 1))


@dataclass(frozen=True, slots=True)
class CheckersOptions:
    mandatory_capture: bool = True
    backward_capture: bool = True
    flying_king: bool = True


class CheckersMoveProvider:
    """Generate complete, atomic moves including maximal capture sequences."""

    def __init__(self, options: CheckersOptions) -> None:
        self.options = options

    def pseudo_legal(self, state: object) -> list[Action]:
        if not isinstance(state, GameState):
            raise TypeError("checkers move provider requires GameState")

        captures: list[MoveAction] = []
        quiet: list[MoveAction] = []
        for index, piece in state.board_state.cells.items():
            if piece is None or piece.side is not state.side_to_move:
                continue
            origin = Square.from_index(
                index,
                state.board_state.board.shape.files,
                state.board_state.board.shape.ranks,
            )
            captures.extend(self._capture_sequences(state, origin, piece))
            quiet.extend(self._quiet_moves(state, origin, piece))

        if not captures:
            return quiet

        maximum = max(len(move.captured_squares) for move in captures)
        maximal = [
            move for move in captures if len(move.captured_squares) == maximum
        ]
        return maximal if self.options.mandatory_capture else maximal + quiet

    def _quiet_moves(
        self, state: GameState, origin: Square, piece: Piece
    ) -> list[MoveAction]:
        is_king = piece.piece_type == KING
        directions = DIAGONALS if is_king else self._forward_directions(piece.side)
        moves: list[MoveAction] = []
        for df, dr in directions:
            current = origin
            while True:
                target = self._step(state, current, df, dr)
                if target is None or not self._empty(state, target, origin):
                    break
                promotion = KING if not is_king and self._promotion_rank(
                    state, target, piece.side
                ) else None
                moves.append(
                    MoveAction(
                        origin,
                        target,
                        promotion_choice=promotion,
                        path=(target,),
                    )
                )
                if not (is_king and self.options.flying_king):
                    break
                current = target
        return moves

    def _capture_sequences(
        self, state: GameState, origin: Square, piece: Piece
    ) -> list[MoveAction]:
        results: list[MoveAction] = []
        self._search_captures(
            state=state,
            origin=origin,
            current=origin,
            side=piece.side,
            is_king=piece.piece_type == KING,
            promoted=False,
            captured=(),
            path=(),
            results=results,
        )
        return results

    def _search_captures(
        self,
        *,
        state: GameState,
        origin: Square,
        current: Square,
        side: PieceSide,
        is_king: bool,
        promoted: bool,
        captured: tuple[int, ...],
        path: tuple[Square, ...],
        results: list[MoveAction],
    ) -> None:
        continuations = (
            self._flying_king_captures(state, origin, current, side, captured)
            if is_king and self.options.flying_king
            else self._short_captures(
                state, origin, current, side, is_king, captured
            )
        )
        if not continuations:
            if captured:
                files = state.board_state.board.shape.files
                results.append(
                    MoveAction(
                        origin,
                        current,
                        promotion_choice=KING if promoted else None,
                        path=path,
                        captured_squares=tuple(
                            Square.from_index(
                                index,
                                files,
                                state.board_state.board.shape.ranks,
                            )
                            for index in captured
                        ),
                    )
                )
            return

        files = state.board_state.board.shape.files
        for landing, victim in continuations:
            now_king = is_king or self._promotion_rank(state, landing, side)
            self._search_captures(
                state=state,
                origin=origin,
                current=landing,
                side=side,
                is_king=now_king,
                promoted=promoted or (not is_king and now_king),
                captured=captured + (victim,),
                path=path + (landing,),
                results=results,
            )

    def _short_captures(
        self,
        state: GameState,
        origin: Square,
        current: Square,
        side: PieceSide,
        is_king: bool,
        captured: tuple[int, ...],
    ) -> list[tuple[Square, int]]:
        directions = (
            DIAGONALS
            if is_king or self.options.backward_capture
            else self._forward_directions(side)
        )
        results: list[tuple[Square, int]] = []
        files = state.board_state.board.shape.files
        for df, dr in directions:
            victim_square = self._step(state, current, df, dr)
            landing = (
                self._step(state, victim_square, df, dr)
                if victim_square is not None
                else None
            )
            if victim_square is None or landing is None:
                continue
            victim_index = victim_square.index(files)
            victim = state.board_state.piece_at(victim_index)
            if (
                victim is not None
                and victim.side not in {side, PieceSide.NEUTRAL}
                and victim_index not in captured
                and self._empty(state, landing, origin)
            ):
                results.append((landing, victim_index))
        return results

    def _flying_king_captures(
        self,
        state: GameState,
        origin: Square,
        current: Square,
        side: PieceSide,
        captured: tuple[int, ...],
    ) -> list[tuple[Square, int]]:
        results: list[tuple[Square, int]] = []
        files = state.board_state.board.shape.files
        for df, dr in DIAGONALS:
            cursor = current
            victim_index: int | None = None
            while True:
                cursor = self._step(state, cursor, df, dr)
                if cursor is None:
                    break
                index = cursor.index(files)
                occupant = self._occupant(state, cursor, origin)
                if occupant is None:
                    if victim_index is not None:
                        results.append((cursor, victim_index))
                    continue
                if victim_index is not None:
                    break
                if (
                    occupant.side in {side, PieceSide.NEUTRAL}
                    or index in captured
                ):
                    break
                victim_index = index
        return results

    @staticmethod
    def _forward_directions(side: PieceSide) -> tuple[tuple[int, int], ...]:
        forward = 1 if side is PieceSide.WHITE else -1
        return ((-1, forward), (1, forward))

    @staticmethod
    def _step(
        state: GameState, square: Square, df: int, dr: int
    ) -> Square | None:
        file = square.file + df
        rank = square.rank + dr
        shape = state.board_state.board.shape
        if 0 <= file < shape.files and 0 <= rank < shape.ranks:
            return Square(file, rank)
        return None

    @staticmethod
    def _promotion_rank(
        state: GameState, square: Square, side: PieceSide
    ) -> bool:
        last = (
            state.board_state.board.shape.ranks - 1
            if side is PieceSide.WHITE
            else 0
        )
        return square.rank == last

    def _empty(
        self, state: GameState, square: Square, origin: Square
    ) -> bool:
        return self._occupant(state, square, origin) is None

    @staticmethod
    def _occupant(
        state: GameState, square: Square, origin: Square
    ) -> Piece | None:
        if square == origin:
            return None
        return state.board_state.piece_at(
            square.index(state.board_state.board.shape.files)
        )
