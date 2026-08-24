"""Composable game mode configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

from chess_core.core.board import Board, BoardShape
from chess_core.core.piece import Piece, PieceCatalog, PieceSide
from chess_core.core.rays import RayTable
from chess_core.core.rules import (
    CaptureSink,
    DropRule,
    LegalityRule,
    PromotionRule,
    StateTransitionRule,
    VictoryCondition,
)
from chess_core.core.topology import FlatTopology, Topology
from chess_core.core.turn import AlternatingSides, TurnOrder, TurnScenario


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
    capture_sink: CaptureSink | None = None
    promotion_rule: PromotionRule | None = None
    legality: LegalityRule | None = None
    transitions: tuple[StateTransitionRule, ...] = field(default_factory=tuple)
    ray_table: RayTable | None = None
    mask_tables: dict[str, int] = field(default_factory=dict)
    start_cells: dict[int, Piece] = field(default_factory=dict)
    initial_extras: dict[str, object] = field(default_factory=dict)
    royal_type: str = "king"
    checks_enabled: bool = True
    asset_family: str = "chess"

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
            side_to_move=PieceSide.WHITE,
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
        self._capture_sink: CaptureSink | None = None
        self._promotion_rule: PromotionRule | None = None
        self._legality: LegalityRule | None = None
        self._transitions: tuple[StateTransitionRule, ...] = ()
        self._ray_table: RayTable | None = None
        self._mask_tables: dict[str, int] = {}
        self._initial_extras: dict[str, object] = {}
        self._royal_type = "king"
        self._checks_enabled = True
        self._asset_family = "chess"

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

    def with_royal_type(self, royal_type: str) -> GameModeBuilder:
        self._royal_type = royal_type
        return self

    def with_checks_enabled(self, enabled: bool) -> GameModeBuilder:
        self._checks_enabled = enabled
        return self

    def with_asset_family(self, family: str) -> GameModeBuilder:
        self._asset_family = family
        return self

    def with_start_cells(self, cells: dict[int, Piece]) -> GameModeBuilder:
        self._start_cells = dict(cells)
        return self

    def with_drop_rule(self, rule: DropRule) -> GameModeBuilder:
        self._drop_rule = rule
        return self

    def with_capture_sink(self, sink: CaptureSink) -> GameModeBuilder:
        self._capture_sink = sink
        return self

    def with_promotion_rule(self, rule: PromotionRule) -> GameModeBuilder:
        self._promotion_rule = rule
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
            capture_sink=self._capture_sink,
            promotion_rule=self._promotion_rule,
            legality=self._legality,
            transitions=self._transitions,
            ray_table=self._ray_table,
            mask_tables=dict(self._mask_tables),
            start_cells=dict(self._start_cells),
            initial_extras=dict(self._initial_extras),
            royal_type=self._royal_type,
            checks_enabled=self._checks_enabled,
            asset_family=self._asset_family,
        )
