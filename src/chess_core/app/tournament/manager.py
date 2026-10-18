"""Tournament manager: lifecycle, late entries, manual pair edits, standings."""

from __future__ import annotations

import uuid

from chess_core.app.tournament.dutch2026 import NativeDutch2026Engine
from chess_core.app.tournament.engine import EngineNotConfiguredError
from chess_core.app.tournament.external import ExternalOfficialEngineAdapter, compare_pairings
from chess_core.app.tournament.models import (
    RESULT_BYE,
    RESULT_HPB,
    RESULT_ZPB,
    AuditEntry,
    Pairing,
    PairingSystem,
    Player,
    PlayerStatus,
    Standing,
    assign_pairing_numbers,
    result_kind_for,
)
from chess_core.app.tournament.pairings import crosstable, pair_round, standings
from chess_core.app.tournament.state import TournamentSettings, TournamentState, new_tournament_state
from chess_core.app.tournament.trf import tournament_to_trf26


class TournamentManager:
    def __init__(
        self,
        state: TournamentState | None = None,
        *,
        native_engine: NativeDutch2026Engine | None = None,
        external_engine: ExternalOfficialEngineAdapter | None = None,
    ) -> None:
        self.state = state or new_tournament_state((), TournamentSettings())
        self.native_engine = native_engine or NativeDutch2026Engine()
        self.external_engine = external_engine or ExternalOfficialEngineAdapter()
        self.last_engine_report: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        players: tuple[Player, ...] | list[Player],
        settings: TournamentSettings | None = None,
        **kwargs,
    ) -> TournamentManager:
        return cls(new_tournament_state(players, settings), **kwargs)

    @property
    def players(self) -> tuple[Player, ...]:
        return self.state.players

    @property
    def pairings(self) -> tuple[Pairing, ...]:
        return self.state.pairings

    @property
    def current_round(self) -> int:
        return self.state.current_round

    def add_player(
        self,
        name: str,
        *,
        rating: int = 0,
        team: str | None = None,
        title: str = "",
        federation: str = "",
        late: bool | None = None,
    ) -> Player:
        if not name.strip():
            raise ValueError("player name is required")
        is_late = self.state.current_round > 0 if late is None else late
        if self.state.settings.list_closed and not is_late:
            raise ValueError("player list is closed")
        player = Player(
            player_id=str(uuid.uuid4()),
            name=name.strip(),
            rating=rating,
            team=team,
            title=title,
            federation=federation,
            status=PlayerStatus.LATE_ENTRY if is_late else PlayerStatus.ACTIVE,
        )
        players = (*self.state.players, player)
        if self.state.current_round < 4:
            players = assign_pairing_numbers(players)
        else:
            next_number = max((item.start_number for item in players), default=0) + 1
            players = tuple(
                item if item.player_id != player.player_id else item.with_start_number(next_number)
                for item in players
            )
        extra: list[Pairing] = []
        if is_late:
            extra.extend(_zero_point_byes_for(player, self.state))
        self.state = self.state.with_players(players).with_pairings(
            (*self.state.pairings, *extra)
        ).append_audit(
            AuditEntry("add_player", "late entry" if is_late else "registration", detail=player.name)
        )
        return player

    def update_player(self, player_id: str, **fields: object) -> Player:
        updated: list[Player] = []
        found: Player | None = None
        for player in self.state.players:
            if player.player_id == player_id:
                found = player.with_updates(**fields)
                updated.append(found)
            else:
                updated.append(player)
        if found is None:
            raise KeyError(f"unknown player: {player_id}")
        if not found.name.strip():
            raise ValueError("player name is required")
        players = tuple(updated)
        if self.can_sort_starting_list():
            players = assign_pairing_numbers(players)
        self.state = self.state.with_players(players).append_audit(
            AuditEntry("edit_player", "player record", detail=found.name)
        )
        return next(player for player in players if player.player_id == player_id)

    def update_settings(self, settings: TournamentSettings) -> TournamentSettings:
        current = self.state.settings
        if self.state.current_round > 0:
            settings = TournamentSettings(
                name=settings.name,
                system=current.system,
                declared_rounds=current.declared_rounds,
                rr_cycles=current.rr_cycles,
                initial_color=current.initial_color,
                pairing_engine=current.pairing_engine,
                seed=current.seed,
                list_closed=settings.list_closed,
                site=settings.site,
                arbiter=settings.arbiter,
                time_control=settings.time_control,
            )
        self.state = self.state.with_settings(settings).append_audit(
            AuditEntry("settings", "updated", detail=settings.name)
        )
        return settings

    def schedule_bye(self, player_id: str, kind: str = RESULT_HPB) -> Player:
        if kind not in {RESULT_HPB, RESULT_ZPB, RESULT_BYE}:
            raise ValueError(f"unsupported bye: {kind}")
        player = self._player(player_id)
        if player.status is PlayerStatus.WITHDRAWN:
            raise ValueError("withdrawn player cannot receive a bye")
        kept = tuple(item for item in self.state.scheduled_byes if item[0] != player_id)
        self.state = self.state.with_scheduled_byes((*kept, (player_id, kind))).append_audit(
            AuditEntry("schedule_bye", kind, detail=player.name)
        )
        return player

    def cancel_scheduled_bye(self, player_id: str) -> None:
        player = self._player(player_id)
        kept = tuple(item for item in self.state.scheduled_byes if item[0] != player_id)
        self.state = self.state.with_scheduled_byes(kept).append_audit(
            AuditEntry("cancel_bye", "cleared", detail=player.name)
        )

    def _player(self, player_id: str) -> Player:
        for player in self.state.players:
            if player.player_id == player_id:
                return player
        raise KeyError(f"unknown player: {player_id}")

    def add_players(self, players: tuple[Player, ...] | list[Player]) -> tuple[Player, ...]:
        added: list[Player] = []
        for player in players:
            added.append(
                self.add_player(
                    player.name,
                    rating=player.rating,
                    team=player.team,
                    title=player.title,
                    federation=player.federation,
                )
            )
        return tuple(added)

    def set_player_status(self, player_id: str, status: PlayerStatus) -> Player:
        updated: list[Player] = []
        found: Player | None = None
        for player in self.state.players:
            if player.player_id == player_id:
                found = player.with_status(status)
                updated.append(found)
            else:
                updated.append(player)
        if found is None:
            raise KeyError(f"unknown player: {player_id}")
        self.state = self.state.with_players(tuple(updated)).append_audit(
            AuditEntry("status", status.value, detail=found.name)
        )
        return found

    def generate_next_round(self) -> tuple[Pairing, ...]:
        settings = self.state.settings
        if self.state.current_round >= _expected_rounds(self.state):
            raise ValueError("all rounds have already been generated")
        unfinished = [
            pairing
            for pairing in self.state.pairings
            if pairing.round_index == self.state.current_round and pairing.result is None
        ]
        if unfinished:
            raise ValueError("current round still has unfinished games")
        next_round = self.state.current_round + 1
        scheduled = dict(self.state.scheduled_byes)
        pairable = [
            player
            for player in self.state.players
            if player.status in {PlayerStatus.ACTIVE, PlayerStatus.LATE_ENTRY}
            and player.player_id not in scheduled
        ]
        skipped = [
            player
            for player in self.state.players
            if player.status is PlayerStatus.ABSENT and player.player_id not in scheduled
        ]
        if len(pairable) < 2:
            raise ValueError("need at least two pairable players")
        if next_round == 1:
            self.sort_starting_list()
            pairable = [
                player
                for player in self.state.players
                if player.status in {PlayerStatus.ACTIVE, PlayerStatus.LATE_ENTRY}
                and player.player_id not in scheduled
            ]
            skipped = [
                player
                for player in self.state.players
                if player.status is PlayerStatus.ABSENT and player.player_id not in scheduled
            ]
        native = pair_round(
            settings.system,
            tuple(pairable),
            self.state.pairings,
            round_index=next_round,
            declared_rounds=_expected_rounds(self.state),
            initial_color=settings.initial_color,
            rr_cycles=settings.rr_cycles,
            pairing_engine=self.native_engine,
        )
        self.last_engine_report = ()
        if settings.system is PairingSystem.SWISS:
            try:
                external = self.external_engine.pair_round(
                    tuple(pairable),
                    self.state.pairings,
                    round_index=next_round,
                    declared_rounds=_expected_rounds(self.state),
                    initial_color=settings.initial_color,
                )
                self.last_engine_report = compare_pairings(native, external)
            except EngineNotConfiguredError:
                self.last_engine_report = ("official pairing engine is not configured",)
        extras: list[Pairing] = []
        for index, (player_id, kind) in enumerate(scheduled.items(), start=1):
            extras.append(Pairing(next_round, 800 + index, player_id, None, kind))
        extras.extend(
            Pairing(next_round, 900 + index, player.player_id, None, RESULT_ZPB)
            for index, player in enumerate(skipped, start=1)
        )
        generated = tuple(native) + tuple(extras)
        self.state = (
            self.state.with_pairings(
                (*self.state.pairings, *generated), current_round=next_round
            )
            .with_scheduled_byes(())
            .append_audit(AuditEntry("pair_round", "generated", round_index=next_round))
        )
        return generated

    def set_result(self, round_index: int, board: int, result: str) -> Pairing:
        updated: list[Pairing] = []
        found: Pairing | None = None
        for pairing in self.state.pairings:
            if pairing.round_index == round_index and pairing.board == board:
                if pairing.is_bye and result not in {RESULT_BYE, RESULT_ZPB, RESULT_HPB}:
                    raise ValueError("bye boards only accept a bye result")
                found = Pairing(
                    pairing.round_index,
                    pairing.board,
                    pairing.white_id,
                    pairing.black_id,
                    result,
                    result_kind=result_kind_for(result),
                    manual=pairing.manual,
                )
                updated.append(found)
            else:
                updated.append(pairing)
        if found is None:
            raise KeyError(f"no pairing for round {round_index} board {board}")
        self.state = self.state.with_pairings(tuple(updated))
        return found

    def replace_round_pairings(
        self,
        round_index: int,
        pairings: tuple[Pairing, ...] | list[Pairing],
        *,
        reason: str,
    ) -> tuple[str, ...]:
        if not reason.strip():
            raise ValueError("manual pairing changes require a reason")
        replaced = [
            Pairing(
                round_index,
                pairing.board,
                pairing.white_id,
                pairing.black_id,
                pairing.result,
                pairing.result_kind,
                True,
            )
            for pairing in pairings
        ]
        warnings = validate_manual_pairings(self.state.players, self.state.pairings, replaced, round_index)
        kept = [pairing for pairing in self.state.pairings if pairing.round_index != round_index]
        merged = tuple(sorted((*kept, *replaced), key=lambda item: (item.round_index, item.board)))
        self.state = self.state.with_pairings(merged, current_round=max(self.state.current_round, round_index)).append_audit(
            AuditEntry("manual_pairings", reason.strip(), round_index=round_index, warnings=warnings)
        )
        return warnings

    def invert_colors(self, round_index: int, board: int, *, reason: str) -> Pairing:
        if not reason.strip():
            raise ValueError("manual pairing changes require a reason")
        updated: list[Pairing] = []
        found: Pairing | None = None
        for pairing in self.state.pairings:
            if pairing.round_index == round_index and pairing.board == board:
                if pairing.is_bye:
                    raise ValueError("cannot invert colours on a bye")
                found = Pairing(
                    pairing.round_index,
                    pairing.board,
                    pairing.black_id,
                    pairing.white_id,
                    pairing.result,
                    pairing.result_kind,
                    True,
                )
                updated.append(found)
            else:
                updated.append(pairing)
        if found is None:
            raise KeyError(f"no pairing for round {round_index} board {board}")
        warnings = ("colours inverted by arbiter",)
        self.state = self.state.with_pairings(tuple(updated)).append_audit(
            AuditEntry("invert_colors", reason.strip(), round_index=round_index, warnings=warnings)
        )
        return found

    def delete_rounds_from(self, round_index: int, *, reason: str = "") -> int:
        """Drop this round and every later one. Players stay; the system can be changed again."""
        if round_index < 1:
            raise ValueError("round index must be at least 1")
        if not any(pairing.round_index >= round_index for pairing in self.state.pairings):
            raise ValueError(f"no pairings from round {round_index} to delete")
        kept = tuple(pairing for pairing in self.state.pairings if pairing.round_index < round_index)
        current = max((pairing.round_index for pairing in kept), default=0)
        self.state = self.state.with_pairings(kept, current_round=current).append_audit(
            AuditEntry(
                "delete_rounds",
                reason.strip() or "rounds removed",
                round_index=round_index,
                detail=f"kept through round {current}",
            )
        )
        return current

    def standings(self) -> tuple[Standing, ...]:
        return standings(self.state.players, self.state.pairings)

    def crosstable(self):
        return crosstable(self.state.players, self.state.pairings)

    def expected_rounds(self) -> int:
        return _expected_rounds(self.state)

    def trf_text(self) -> str:
        return tournament_to_trf26(
            name=self.state.settings.name,
            players=self.state.players,
            pairings=self.state.pairings,
            declared_rounds=max(self.expected_rounds(), self.state.current_round),
            site=self.state.settings.site,
            arbiter=self.state.settings.arbiter,
            time_control=self.state.settings.time_control,
            system=self.state.settings.system,
        )

    def pairings_text(self, round_index: int | None = None) -> str:
        target = self.state.current_round if round_index is None else round_index
        names = self.state.player_map()
        lines = [self.state.settings.name, f"Тур {target}"]
        for pairing in self.round_pairings(target):
            white = names.get(pairing.white_id or "")
            black = names.get(pairing.black_id or "")
            white_name = _player_label(white) if white is not None else "BYE"
            black_name = _player_label(black) if black is not None else "BYE"
            result = pairing.result or "—"
            lines.append(f"{pairing.board}. {white_name} — {black_name}  {result}")
        return "\n".join(lines)

    def can_sort_starting_list(self) -> bool:
        """FIDE: TPNs may be corrected until the fourth round has been paired."""
        return self.state.current_round < 4

    def starting_list(self) -> tuple[Player, ...]:
        numbered = [player for player in self.state.players if player.start_number]
        if len(numbered) == len(self.state.players):
            return tuple(sorted(self.state.players, key=lambda player: player.start_number))
        return assign_pairing_numbers(self.state.players)

    def sort_starting_list(self) -> tuple[Player, ...]:
        if not self.can_sort_starting_list():
            raise ValueError("стартовые номера нельзя менять после жеребьёвки 4-го тура")
        players = assign_pairing_numbers(self.state.players)
        if players != self.state.players:
            self.state = self.state.with_players(players).append_audit(
                AuditEntry("sort_starting_list", "rating, title, name")
            )
        else:
            self.state = self.state.with_players(players)
        return players

    def alphabetical_players(self) -> tuple[Player, ...]:
        return tuple(sorted(self.state.players, key=lambda player: (player.name.casefold(), player.start_number)))

    def round_pairings(self, round_index: int | None = None) -> tuple[Pairing, ...]:
        target = self.state.current_round if round_index is None else round_index
        return tuple(
            pairing
            for pairing in self.state.pairings
            if pairing.round_index == target
        )


def _player_label(player: Player) -> str:
    title = f"{player.title} " if player.title else ""
    rating = f" ({player.rating})" if player.rating else ""
    return f"{title}{player.name}{rating}".strip()


def validate_manual_pairings(
    players: tuple[Player, ...],
    history: tuple[Pairing, ...],
    proposed: list[Pairing],
    round_index: int,
) -> tuple[str, ...]:
    warnings: list[str] = []
    names = {player.player_id: player.name for player in players}
    seen: set[str] = set()
    previous_pairs = {
        frozenset(pairing.player_ids())
        for pairing in history
        if pairing.round_index != round_index and not pairing.is_bye
    }
    for pairing in proposed:
        ids = pairing.player_ids()
        for player_id in ids:
            if player_id in seen:
                warnings.append(f"{names.get(player_id, player_id)} paired more than once")
            seen.add(player_id)
        if not pairing.is_bye:
            key = frozenset(ids)
            if key in previous_pairs:
                warnings.append("repeat pairing: " + " vs ".join(names.get(item, item) for item in ids))
    pairable = {
        player.player_id
        for player in players
        if player.status in {PlayerStatus.ACTIVE, PlayerStatus.LATE_ENTRY}
    }
    missing = pairable - seen
    if missing:
        warnings.append("unpaired players: " + ", ".join(names.get(item, item) for item in sorted(missing)))
    return tuple(warnings)


def _expected_rounds(state: TournamentState) -> int:
    n = len(state.players)
    settings = state.settings
    if settings.system is PairingSystem.ROUND_ROBIN:
        per_cycle = n if n % 2 else n - 1
        return max(1, per_cycle * settings.rr_cycles)
    if settings.system.is_swiss:
        return settings.declared_rounds or max(1, n.bit_length())
    return settings.declared_rounds


def _zero_point_byes_for(player: Player, state: TournamentState) -> list[Pairing]:
    extras: list[Pairing] = []
    for round_index in range(1, state.current_round + 1):
        already = any(
            player.player_id in pairing.player_ids() and pairing.round_index == round_index
            for pairing in state.pairings
        )
        if already:
            continue
        extras.append(Pairing(round_index, 800 + round_index, player.player_id, None, RESULT_ZPB))
    return extras
