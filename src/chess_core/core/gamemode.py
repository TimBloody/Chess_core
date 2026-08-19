"""Composable game mode configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

from chess_core.core.board import Board, BoardShape
from chess_core.core.piece import MovePatternResolver, Piece, PieceCatalog, PieceSide
from chess_core.core.rays import RayTable
from chess_core.core.rules import (
    CastlingRule,
    DropRule,
    LegalityRule,
    PromotionRule,
    StateTransitionRule,
    VictoryCondition,
    VictoryKind,
)
from chess_core.core.topology import FlatTopology, Topology
from chess_core.core.turn import AlternatingSides, StaticTurnPolicy, TurnOrder, TurnPolicy, TurnScenario


@dataclass
class GameMode:
    """Full ruleset: board, topology, pieces, turn scenario, victory."""

    id: str
    name: str
    board: Board
    topology: Topology
    pieces: PieceCatalog
    turn_scenario: TurnScenario
    turn_order: TurnOrder
    victory: VictoryCondition | tuple[VictoryCondition, ...]
    drop_rule: DropRule | None = None
    promotion_rule: PromotionRule | None = None
    castling_rule: CastlingRule | None = None
    legality: LegalityRule | None = None
    transitions: tuple[StateTransitionRule, ...] = field(default_factory=tuple)
    ray_table: RayTable | None = None
    mask_tables: dict[str, int] = field(default_factory=dict)
    start_cells: dict[int, Piece] = field(default_factory=dict)
    initial_extras: dict[str, object] = field(default_factory=dict)
    starting_side: PieceSide = PieceSide.WHITE
    default_view_side: PieceSide = PieceSide.WHITE
    asset_family: str = "chess"
    facing_opponent: bool = False
    is_dummy: bool = False
    modifier_ids: tuple[str, ...] = field(default_factory=tuple)
    turn_policy: TurnPolicy | None = None
    move_resolver: MovePatternResolver | None = None

    def piece_is_royal(self, piece: Piece) -> bool:
        try:
            return self.pieces.get(piece.piece_type).is_royal
        except KeyError:
            return piece.piece_type.name == "king"

    def victory_conditions(self) -> tuple[VictoryCondition, ...]:
        if isinstance(self.victory, tuple):
            return self.victory
        return (self.victory,)

    def victory_kinds(self) -> tuple[VictoryKind, ...]:
        return tuple(condition.kind for condition in self.victory_conditions())

    def lose_on_no_legal_moves(self) -> bool:
        return all(
            condition.lose_on_no_legal_moves for condition in self.victory_conditions()
        )

    def protects_royal(self) -> bool:
        """True when self-check is illegal (mate or safe-try victories)."""
        kinds = self.victory_kinds()
        return (
            VictoryKind.CHECKMATE in kinds
            or VictoryKind.KING_REACHES_ZONE in kinds
            or VictoryKind.THREE_CHECK in kinds
        )

    def allows_royal_capture(self) -> bool:
        return VictoryKind.KING_CAPTURE in self.victory_kinds()

    def initial_state(self) -> object:
        from chess_core.core.state import BoardState, GameState, HandsState

        cells: dict[int, Piece | None] = {
            index: None for index in range(self.board.shape.cell_count)
        }
        cells.update(self.start_cells)
        extras: dict[str, object] = dict(self.initial_extras)
        extras["mode"] = self
        return GameState(
            board_state=BoardState(self.board, cells),
            side_to_move=self.starting_side,
            hands=HandsState() if self.drop_rule is not None else None,
            extras=extras,
        )


class GameModeBuilder:
    """Fluent builder for GameMode."""

    def __init__(self, mode_id: str, name: str) -> None:
        self._id = mode_id
        self._name = name
        self._shape: BoardShape | None = None
        self._topology: Topology | None = None
        self._catalog: PieceCatalog | None = None
        self._turn_scenario: TurnScenario | None = None
        self._turn_order: TurnOrder | None = None
        self._victory: VictoryCondition | tuple[VictoryCondition, ...] | None = None
        self._start_cells: dict[int, Piece] = {}
        self._drop_rule: DropRule | None = None
        self._promotion_rule: PromotionRule | None = None
        self._castling_rule: CastlingRule | None = None
        self._legality: LegalityRule | None = None
        self._transitions: tuple[StateTransitionRule, ...] = ()
        self._ray_table: RayTable | None = None
        self._mask_tables: dict[str, int] = {}
        self._initial_extras: dict[str, object] = {}
        self._starting_side: PieceSide = PieceSide.WHITE
        self._default_view_side: PieceSide = PieceSide.WHITE
        self._asset_family: str = "chess"
        self._facing_opponent: bool = False
        self._is_dummy: bool = False
        self._modifier_ids: tuple[str, ...] = ()
        self._turn_policy: TurnPolicy | None = None
        self._move_resolver: MovePatternResolver | None = None

    def with_shape(self, files: int, ranks: int) -> GameModeBuilder:
        self._shape = BoardShape(files=files, ranks=ranks)
        return self

    def with_topology(self, topology: Topology) -> GameModeBuilder:
        self._topology = topology
        return self

    def with_pieces(self, catalog: PieceCatalog) -> GameModeBuilder:
        self._catalog = catalog
        return self

    def with_turn_scenario(self, scenario: TurnScenario) -> GameModeBuilder:
        self._turn_scenario = scenario
        return self

    def with_turn_order(self, order: TurnOrder) -> GameModeBuilder:
        self._turn_order = order
        return self

    def with_victory(
        self, condition: VictoryCondition | tuple[VictoryCondition, ...]
    ) -> GameModeBuilder:
        self._victory = condition
        return self

    def with_start_cells(self, cells: dict[int, Piece]) -> GameModeBuilder:
        self._start_cells = dict(cells)
        return self

    def with_drop_rule(self, rule: DropRule) -> GameModeBuilder:
        self._drop_rule = rule
        return self

    def with_promotion_rule(self, rule: PromotionRule) -> GameModeBuilder:
        self._promotion_rule = rule
        return self

    def with_castling_rule(self, rule: CastlingRule) -> GameModeBuilder:
        self._castling_rule = rule
        return self

    def with_legality(self, rule: LegalityRule) -> GameModeBuilder:
        self._legality = rule
        return self

    def with_transitions(
        self, transitions: tuple[StateTransitionRule, ...]
    ) -> GameModeBuilder:
        self._transitions = transitions
        return self

    def with_ray_table(self, table: RayTable) -> GameModeBuilder:
        self._ray_table = table
        return self

    def with_mask_tables(self, masks: dict[str, int]) -> GameModeBuilder:
        self._mask_tables = dict(masks)
        return self

    def with_initial_extras(self, extras: dict[str, object]) -> GameModeBuilder:
        self._initial_extras = dict(extras)
        return self

    def with_starting_side(self, side: PieceSide) -> GameModeBuilder:
        self._starting_side = side
        return self

    def with_default_view_side(self, side: PieceSide) -> GameModeBuilder:
        self._default_view_side = side
        return self

    def with_asset_family(self, family: str) -> GameModeBuilder:
        self._asset_family = family
        return self

    def with_facing_opponent(self, enabled: bool = True) -> GameModeBuilder:
        self._facing_opponent = enabled
        return self

    def with_is_dummy(self, is_dummy: bool = True) -> GameModeBuilder:
        self._is_dummy = is_dummy
        return self

    def with_modifier_ids(self, modifier_ids: tuple[str, ...]) -> GameModeBuilder:
        self._modifier_ids = tuple(modifier_ids)
        return self

    def with_turn_policy(self, policy: TurnPolicy) -> GameModeBuilder:
        self._turn_policy = policy
        return self

    def with_move_resolver(self, resolver: MovePatternResolver) -> GameModeBuilder:
        self._move_resolver = resolver
        return self

    def with_shogi_presentation(self) -> GameModeBuilder:
        """Sente is BLACK on the last rank; the board is shown from that side."""
        return (
            self.with_starting_side(PieceSide.BLACK)
            .with_default_view_side(PieceSide.BLACK)
            .with_asset_family("shogi")
            .with_facing_opponent(True)
        )

    def build(self) -> GameMode:
        if self._shape is None:
            raise ValueError("GameMode shape is required")
        if self._catalog is None:
            raise ValueError("GameMode piece catalog is required")
        if self._turn_scenario is None:
            raise ValueError("GameMode turn scenario is required")
        if self._victory is None:
            raise ValueError("GameMode victory condition is required")

        topology = self._topology or FlatTopology(self._shape)
        turn_order = self._turn_order or AlternatingSides(
            (PieceSide.WHITE, PieceSide.BLACK)
        )
        turn_policy = self._turn_policy or StaticTurnPolicy(self._turn_scenario)
        for index in self._start_cells:
            if not 0 <= index < self._shape.cell_count:
                raise ValueError(f"start cell {index} is outside the board")

        return GameMode(
            id=self._id,
            name=self._name,
            board=Board(self._shape),
            topology=topology,
            pieces=self._catalog,
            turn_scenario=self._turn_scenario,
            turn_order=turn_order,
            victory=self._victory,
            drop_rule=self._drop_rule,
            promotion_rule=self._promotion_rule,
            castling_rule=self._castling_rule,
            legality=self._legality,
            transitions=self._transitions,
            ray_table=self._ray_table,
            mask_tables=dict(self._mask_tables),
            start_cells=dict(self._start_cells),
            initial_extras=dict(self._initial_extras),
            starting_side=self._starting_side,
            default_view_side=self._default_view_side,
            asset_family=self._asset_family,
            facing_opponent=self._facing_opponent,
            is_dummy=self._is_dummy,
            modifier_ids=self._modifier_ids,
            turn_policy=turn_policy,
            move_resolver=self._move_resolver,
        )
