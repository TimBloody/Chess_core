"""Move generation (pseudo-legal and legal)."""

from __future__ import annotations

from chess_core.core.board import Square
from chess_core.core.gamemode import GameMode
from chess_core.core.move import Action, DropAction, MoveAction, Turn
from chess_core.core.piece import MovePatternKind, Piece, PieceSide, PieceTypeId
from chess_core.core.rules import VictoryCondition, VictoryKind
from chess_core.core.state import GameState


class MoveGenerator:
    def __init__(self, mode: GameMode) -> None:
        self._mode = mode

    def generate_pseudo_legal(self, state: GameState) -> list[Action]:
        self._validate_state_shape(state)
        moves: list[Action] = []
        shape = self._mode.board.shape
        for origin_index in range(shape.cell_count):
            moves.extend(self._pseudo_for_index(state, origin_index))
        moves.extend(self._drop_pseudo(state))
        return list(dict.fromkeys(moves))

    def generate_legal(self, state: GameState) -> list[Action]:
        return self._filter_legal(state, self.generate_pseudo_legal(state))

    def generate_legal_for_square(
        self, state: GameState, square: Square | int
    ) -> list[Action]:
        """Generate legal actions originating only from ``square``.

        King safety is checked exactly as in :meth:`generate_legal`, so pinned
        pieces and mandatory check evasions remain correctly filtered.
        """
        self._validate_state_shape(state)
        index = self._square_index(square)
        return self._filter_legal(state, self._pseudo_for_index(state, index))

    def has_any_legal(self, state: GameState) -> bool:
        """Return early when the position has at least one legal action."""
        self._validate_state_shape(state)
        for index in range(self._mode.board.shape.cell_count):
            if self.generate_legal_for_square(state, index):
                return True
        return bool(self._filter_legal(state, self._drop_pseudo(state)))

    def _filter_legal(
        self, state: GameState, pseudo: list[Action]
    ) -> list[Action]:
        legal: list[Action] = []
        for action in pseudo:
            if not isinstance(action, (MoveAction, DropAction)):
                legal.append(action)
                continue
            try:
                result = state.apply_turn(Turn(state.side_to_move, [action]), record_history=False)
            except ValueError:
                continue
            if self._mode.checks_enabled and self._king_is_attacked(result, state.side_to_move):
                continue
            if self._is_forbidden_checkmate_drop(action, result):
                continue
            legal.append(action)
        if self._mode.legality is not None:
            return self._mode.legality.filter_legal(legal, state)
        return legal

    def _pseudo_for_index(self, state: GameState, origin_index: int) -> list[Action]:
        shape = self._mode.board.shape
        piece = state.board_state.piece_at(origin_index)
        if piece is None or piece.side is not state.side_to_move:
            return []
        origin = Square.from_index(origin_index, shape.files, shape.ranks)
        moves: list[Action] = []
        piece_type = self._mode.pieces.get(piece.piece_type)
        for pattern in piece_type.patterns:
            if pattern.kind is MovePatternKind.LEAP:
                moves.extend(
                    self._leap_moves(state, piece, origin, pattern.directions)
                )
            elif pattern.kind is MovePatternKind.SLIDE:
                moves.extend(
                    self._slide_moves(state, piece, origin, pattern.directions)
                )
            elif pattern.pattern_key == "pawn":
                moves.extend(self._pawn_moves(state, piece, origin))
        if piece.piece_type.name == "king":
            moves.extend(self._castling_moves(state))
        return moves

    def _square_index(self, square: Square | int) -> int:
        shape = self._mode.board.shape
        if isinstance(square, Square):
            index = square.index(shape.files)
            if Square.from_index(index, shape.files, shape.ranks) != square:
                raise ValueError("square is outside the game board")
            return index
        if not isinstance(square, int):
            raise TypeError("square must be a Square or integer index")
        Square.from_index(square, shape.files, shape.ranks)
        return square

    def is_in_check(
        self, state: GameState, side: PieceSide | None = None
    ) -> bool:
        """Return whether ``side`` (the side to move by default) is in check."""
        self._validate_state_shape(state)
        return self._king_is_attacked(state, side or state.side_to_move)

    def is_square_attacked(
        self, state: GameState, square: Square, by_side: PieceSide
    ) -> bool:
        """Public attack-map query used by game status and clients."""
        self._validate_state_shape(state)
        return self._square_attacked(state, square, by_side)

    def is_checkmate(self, state: GameState) -> bool:
        return self.is_in_check(state) and not self.has_any_legal(state)

    def is_stalemate(self, state: GameState) -> bool:
        return not self.is_in_check(state) and not self.has_any_legal(state)

    def _leap_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        offsets: tuple[tuple[int, int], ...],
    ) -> list[MoveAction]:
        moves: list[MoveAction] = []
        for offset in offsets:
            if piece.side is PieceSide.BLACK:
                offset = (offset[0], -offset[1])
            target = self._mode.topology.step(origin, offset)
            if target is not None and self._can_land(state, piece, target):
                moves.extend(self._with_configured_promotions(state, piece, origin, target))
        return moves

    def _slide_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        directions: tuple[tuple[int, int], ...],
    ) -> list[MoveAction]:
        moves: list[MoveAction] = []
        files = self._mode.board.shape.files
        for direction in directions:
            if piece.side is PieceSide.BLACK:
                direction = (direction[0], -direction[1])
            current = origin
            visited = {origin.index(files)}
            while True:
                target = self._mode.topology.step(current, direction)
                if target is None:
                    break
                target_index = target.index(files)
                if target_index in visited:
                    break
                visited.add(target_index)
                occupant = state.board_state.piece_at(target_index)
                if occupant is None:
                    moves.extend(self._with_configured_promotions(state, piece, origin, target))
                    current = target
                    continue
                if self._can_capture(piece, occupant):
                    moves.extend(self._with_configured_promotions(state, piece, origin, target))
                break
        return moves

    def _pawn_moves(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
    ) -> list[MoveAction]:
        direction = 1 if piece.side is PieceSide.WHITE else -1
        start_rank = 1 if piece.side is PieceSide.WHITE else self._mode.board.shape.ranks - 2
        moves: list[MoveAction] = []
        one_step = self._mode.topology.step(origin, (0, direction))
        if one_step is not None and self._is_empty(state, one_step):
            moves.extend(self._with_promotions(origin, one_step, piece.side))
            two_step = self._mode.topology.step(one_step, (0, direction))
            if (
                origin.rank == start_rank
                and two_step is not None
                and self._is_empty(state, two_step)
            ):
                moves.append(MoveAction(origin, two_step))

        en_passant = state.extras.get("en_passant")
        for file_delta in (-1, 1):
            target = self._mode.topology.step(origin, (file_delta, direction))
            if target is None:
                continue
            occupant = state.board_state.piece_at(
                target.index(self._mode.board.shape.files)
            )
            if (
                occupant is not None and self._can_capture(piece, occupant)
            ) or (
                target == en_passant
                and self._valid_en_passant_victim(state, piece, target)
            ):
                moves.extend(self._with_promotions(origin, target, piece.side))
        return moves

    def _with_promotions(
        self,
        origin: Square,
        target: Square,
        side: PieceSide,
    ) -> list[MoveAction]:
        last_rank = self._mode.board.shape.ranks - 1 if side is PieceSide.WHITE else 0
        if target.rank != last_rank:
            return [MoveAction(origin, target)]
        choices = ("queen", "rook", "bishop", "knight")
        if self._mode.initial_extras.get("promote_includes_king"):
            choices = (*choices, "king")
        available = {piece_type.id.name for piece_type in self._mode.pieces.all_types()}
        return [
            MoveAction(origin, target, PieceTypeId(choice))
            for choice in choices
            if choice in available
        ]

    def _with_configured_promotions(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        target: Square,
    ) -> list[MoveAction]:
        rule = self._mode.promotion_rule
        can_promote = getattr(rule, "can_promote", None)
        must_promote = getattr(rule, "must_promote", None)
        if rule is None or not callable(can_promote):
            return [MoveAction(origin, target)]
        if callable(must_promote) and must_promote(piece, origin, target, state):
            choices = rule.choices(piece.piece_type)
            return [MoveAction(origin, target, choice) for choice in choices] or [
                MoveAction(origin, target)
            ]
        if can_promote(piece, origin, target, state):
            promoted = [MoveAction(origin, target, choice) for choice in rule.choices(piece.piece_type)]
            return [MoveAction(origin, target), *promoted]
        return [MoveAction(origin, target)]

    def _is_forbidden_checkmate_drop(self, action: Action, result: GameState) -> bool:
        if not isinstance(action, DropAction) or self._mode.drop_rule is None:
            return False
        forbids = getattr(self._mode.drop_rule, "forbids_checkmate_drop", None)
        if not callable(forbids) or not forbids(action.piece_type):
            return False
        if getattr(self, "_in_drop_mate_probe", False):
            return False
        self._in_drop_mate_probe = True
        try:
            return self.is_checkmate(result)
        finally:
            self._in_drop_mate_probe = False

    def _castling_moves(self, state: GameState) -> list[MoveAction]:
        if self._mode.board.shape.files != 8 or self._mode.board.shape.ranks != 8:
            return []
        side = state.side_to_move
        rank = 0 if side is PieceSide.WHITE else 7
        rights = set(state.extras.get("castling_rights", ()))
        if not rights:
            return []
        king_index, king = next(
            (
                (index, piece)
                for index, piece in state.board_state.cells.items()
                if piece is not None
                and piece.piece_type.name == "king"
                and piece.side is side
                and index // 8 == rank
            ),
            (None, None),
        )
        if king_index is None or king is None:
            return []
        origin = Square.from_index(king_index, 8, 8)
        enemy = PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE
        if self._square_attacked(state, origin, enemy):
            return []
        rook_files = state.extras.get("castling_rooks")
        if isinstance(rook_files, dict):
            return self._chess960_castling_moves(state, origin, side, rank, rights, rook_files, enemy)
        return self._classic_castling_moves(state, origin, side, rank, rights, enemy)

    def _classic_castling_moves(
        self,
        state: GameState,
        origin: Square,
        side: PieceSide,
        rank: int,
        rights: set[object],
        enemy: PieceSide,
    ) -> list[MoveAction]:
        candidates: list[MoveAction] = []
        right_prefix = "K" if side is PieceSide.WHITE else "k"
        for right, rook_file, path, transit, target_file in (
            (right_prefix, 7, (5, 6), (5, 6), 6),
            (right_prefix.lower() if side is PieceSide.WHITE else "q", 0, (1, 2, 3), (3, 2), 2),
        ):
            if side is PieceSide.WHITE and rook_file == 0:
                right = "Q"
            rook = state.board_state.piece_at(rank * 8 + rook_file)
            if (
                right in rights
                and rook is not None
                and rook.piece_type.name == "rook"
                and rook.side is side
                and all(state.board_state.piece_at(rank * 8 + file) is None for file in path)
                and all(
                    not self._square_attacked(state, Square(file, rank), enemy)
                    for file in transit
                )
            ):
                candidates.append(MoveAction(origin, Square(target_file, rank)))
        return candidates

    def _chess960_castling_moves(
        self,
        state: GameState,
        origin: Square,
        side: PieceSide,
        rank: int,
        rights: set[object],
        rook_files: dict[object, object],
        enemy: PieceSide,
    ) -> list[MoveAction]:
        candidates: list[MoveAction] = []
        for right, dest_file, rook_dest in (
            ("K" if side is PieceSide.WHITE else "k", 6, 5),
            ("Q" if side is PieceSide.WHITE else "q", 2, 3),
        ):
            if right not in rights:
                continue
            rook_file = rook_files.get(right)
            if not isinstance(rook_file, int):
                continue
            rook = state.board_state.piece_at(rank * 8 + rook_file)
            if rook is None or rook.piece_type.name != "rook" or rook.side is not side:
                continue
            king_path = _inclusive_files(origin.file, dest_file)
            rook_path = _inclusive_files(rook_file, rook_dest)
            blocked = (set(king_path) | set(rook_path)) - {origin.file, rook_file}
            if any(state.board_state.piece_at(rank * 8 + file) is not None for file in blocked):
                continue
            if any(self._square_attacked(state, Square(file, rank), enemy) for file in king_path):
                continue
            candidates.append(MoveAction(origin, Square(rook_file, rank)))
        return candidates

    def _king_is_attacked(self, state: GameState, side: PieceSide) -> bool:
        shape = self._mode.board.shape
        king_square = next(
            (
                Square.from_index(index, shape.files, shape.ranks)
                for index, piece in state.board_state.cells.items()
                if piece is not None
                and piece.side is side
                and piece.piece_type.name == self._mode.royal_type
            ),
            None,
        )
        if king_square is None:
            return False
        enemy = PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE
        return self._square_attacked(state, king_square, enemy)

    def _square_attacked(
        self,
        state: GameState,
        square: Square,
        by_side: PieceSide,
    ) -> bool:
        shape = self._mode.board.shape
        for index, piece in state.board_state.cells.items():
            if piece is None or piece.side is not by_side:
                continue
            origin = Square.from_index(index, shape.files, shape.ranks)
            piece_type = self._mode.pieces.get(piece.piece_type)
            for pattern in piece_type.patterns:
                if pattern.pattern_key == "pawn":
                    direction = 1 if by_side is PieceSide.WHITE else -1
                    if any(
                        self._mode.topology.step(origin, (df, direction)) == square
                        for df in (-1, 1)
                    ):
                        return True
                elif pattern.kind is MovePatternKind.LEAP:
                    if any(
                        self._mode.topology.step(
                            origin,
                            (offset[0], -offset[1])
                            if piece.side is PieceSide.BLACK
                            else offset,
                        )
                        == square
                        for offset in pattern.directions
                    ):
                        return True
                elif pattern.kind is MovePatternKind.SLIDE:
                    if self._slider_attacks(
                        state, piece, origin, pattern.directions, square
                    ):
                        return True
        return False

    def _slider_attacks(
        self,
        state: GameState,
        piece: Piece,
        origin: Square,
        directions: tuple[tuple[int, int], ...],
        square: Square,
    ) -> bool:
        files = self._mode.board.shape.files
        for direction in directions:
            if piece.side is PieceSide.BLACK:
                direction = (direction[0], -direction[1])
            current = origin
            visited = {origin.index(files)}
            while True:
                target = self._mode.topology.step(current, direction)
                if target is None or target.index(files) in visited:
                    break
                if target == square:
                    return True
                visited.add(target.index(files))
                if state.board_state.piece_at(target.index(files)) is not None:
                    break
                current = target
        return False

    def _can_land(self, state: GameState, piece: Piece, target: Square) -> bool:
        occupant = state.board_state.piece_at(
            target.index(self._mode.board.shape.files)
        )
        return occupant is None or self._can_capture(piece, occupant)

    def _can_capture(self, piece: Piece, occupant: Piece) -> bool:
        if occupant.side is piece.side or occupant.side is PieceSide.NEUTRAL:
            return False
        if occupant.piece_type.name == self._mode.royal_type and self._uses_checkmate_victory():
            return False
        return True

    def _uses_checkmate_victory(self) -> bool:
        conditions = (
            self._mode.victory
            if isinstance(self._mode.victory, tuple)
            else (self._mode.victory,)
        )
        return any(
            isinstance(condition, VictoryCondition)
            and condition.kind is VictoryKind.CHECKMATE
            for condition in conditions
        )

    def _valid_en_passant_victim(
        self, state: GameState, piece: Piece, target: Square
    ) -> bool:
        files = self._mode.board.shape.files
        target_index = target.index(files)
        victim_index = (
            target_index - files
            if piece.side is PieceSide.WHITE
            else target_index + files
        )
        victim = state.board_state.piece_at(victim_index)
        return (
            victim is not None
            and victim.piece_type.name == "pawn"
            and victim.side is not piece.side
            and victim.side is not PieceSide.NEUTRAL
        )

    def _is_empty(self, state: GameState, square: Square) -> bool:
        return (
            state.board_state.piece_at(square.index(self._mode.board.shape.files))
            is None
        )

    def _drop_pseudo(self, state: GameState) -> list[Action]:
        if self._mode.drop_rule is None or state.hands is None:
            return []
        hand = state.hands.by_side.get(state.side_to_move, ())
        type_names = {piece.piece_type.name for piece in hand}
        if not type_names:
            return []
        shape = self._mode.board.shape
        drops: list[Action] = []
        for name in type_names:
            piece_type = PieceTypeId(name)
            faces = self._mode.drop_rule.allowed_faces(piece_type)
            for index in range(shape.cell_count):
                if not self._mode.drop_rule.can_drop(piece_type, index, state):
                    continue
                square = Square.from_index(index, shape.files, shape.ranks)
                if faces is None:
                    drops.append(DropAction(piece_type, square))
                else:
                    drops.extend(DropAction(piece_type, square, face) for face in faces)
        return drops

    def _validate_state_shape(self, state: GameState) -> None:
        if state.board_state.board.shape != self._mode.board.shape:
            raise ValueError("state board shape does not match game mode")


def _inclusive_files(start: int, end: int) -> tuple[int, ...]:
    step = 1 if end >= start else -1
    return tuple(range(start, end + step, step))
