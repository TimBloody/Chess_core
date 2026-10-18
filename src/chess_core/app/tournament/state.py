"""In-memory tournament snapshot. No I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace

from chess_core.app.tournament.models import (
    AuditEntry,
    Pairing,
    PairingSystem,
    Player,
    PlayerStatus,
    assign_pairing_numbers,
)


@dataclass(frozen=True, slots=True)
class TournamentSettings:
    name: str = "Tournament"
    system: PairingSystem = PairingSystem.SWISS
    declared_rounds: int = 5
    rr_cycles: int = 1
    initial_color: str = "white"
    pairing_engine: str = "native_dutch_2026"
    seed: int = 1
    list_closed: bool = False
    site: str = ""
    arbiter: str = ""
    time_control: str = ""


@dataclass(frozen=True, slots=True)
class TournamentState:
    settings: TournamentSettings
    players: tuple[Player, ...]
    pairings: tuple[Pairing, ...] = ()
    current_round: int = 0
    audit: tuple[AuditEntry, ...] = ()
    scheduled_byes: tuple[tuple[str, str], ...] = ()
    version: int = 1

    def with_players(self, players: tuple[Player, ...]) -> TournamentState:
        return replace(self, players=players)

    def with_settings(self, settings: TournamentSettings) -> TournamentState:
        return replace(self, settings=settings)

    def with_scheduled_byes(self, scheduled_byes: tuple[tuple[str, str], ...]) -> TournamentState:
        return replace(self, scheduled_byes=scheduled_byes)

    def with_pairings(self, pairings: tuple[Pairing, ...], current_round: int | None = None) -> TournamentState:
        round_index = self.current_round if current_round is None else current_round
        return replace(self, pairings=pairings, current_round=round_index)

    def append_audit(self, entry: AuditEntry) -> TournamentState:
        return replace(self, audit=(*self.audit, entry))

    def player_map(self) -> dict[str, Player]:
        return {player.player_id: player for player in self.players}

    def pairable_players(self) -> tuple[Player, ...]:
        return tuple(
            player
            for player in self.players
            if player.status in {PlayerStatus.ACTIVE, PlayerStatus.LATE_ENTRY}
        )


def new_tournament_state(
    players: tuple[Player, ...] | list[Player],
    settings: TournamentSettings | None = None,
) -> TournamentState:
    numbered = assign_pairing_numbers(players)
    return TournamentState(settings=settings or TournamentSettings(), players=numbered)
