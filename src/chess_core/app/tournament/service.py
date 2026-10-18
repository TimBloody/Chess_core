"""Application service for tournament draws."""

from __future__ import annotations

import random

from chess_core.app.tournament.dutch2026 import NativeDutch2026Engine
from chess_core.app.tournament.models import (
    VALID_RESULTS,
    Pairing,
    PairingSystem,
    Player,
    Standing,
    assign_pairing_numbers,
    result_kind_for,
)
from chess_core.app.tournament.pairings import pair_round, standings


class TournamentService:
    def __init__(
        self,
        system: PairingSystem,
        players: tuple[Player, ...] | list[Player],
        *,
        swiss_rounds: int = 0,
        seed: int | None = None,
        rr_cycles: int = 1,
        initial_color: str = "white",
        pairing_engine: NativeDutch2026Engine | None = None,
    ) -> None:
        self.system = system
        self.players = tuple(players)
        if len(self.players) < 2:
            raise ValueError("tournament needs at least two players")
        self.swiss_rounds = swiss_rounds
        self.rr_cycles = rr_cycles
        self.initial_color = initial_color
        self.pairing_engine = pairing_engine
        self._rng = random.Random(seed)
        self._pairings: list[Pairing] = []
        self._round = 0

    @property
    def pairings(self) -> tuple[Pairing, ...]:
        return tuple(self._pairings)

    @property
    def current_round(self) -> int:
        return self._round

    def expected_rounds(self) -> int:
        n = len(self.players)
        if self.system is PairingSystem.ROUND_ROBIN:
            per_cycle = n if n % 2 else n - 1
            return per_cycle * max(1, self.rr_cycles)
        if self.system.is_swiss:
            return self.swiss_rounds or max(1, n.bit_length())
        if self.system is PairingSystem.KNOCKOUT:
            size = 1
            while size < n:
                size *= 2
            rounds = 0
            while size > 1:
                size //= 2
                rounds += 1
            return rounds
        if self.system is PairingSystem.SCHEVENINGEN:
            teams = {player.team for player in self.players}
            if len(teams) != 2:
                return 0
            per_team = n // 2
            return per_team
        return 1

    def generate_next_round(self) -> tuple[Pairing, ...]:
        if self._round >= self.expected_rounds() and self.system is not PairingSystem.COLOR_DRAW:
            raise ValueError("all rounds have already been generated")
        unfinished = [
            pairing
            for pairing in self._pairings
            if pairing.round_index == self._round and pairing.result is None
        ]
        if unfinished:
            raise ValueError("current round still has unfinished games")
        next_round = self._round + 1
        if next_round == 1 and (
            self.system.is_swiss or self.system is PairingSystem.ROUND_ROBIN
        ):
            self.players = assign_pairing_numbers(self.players)
        generated = pair_round(
            self.system,
            self.players,
            tuple(self._pairings),
            round_index=next_round,
            rng=self._rng,
            declared_rounds=self.expected_rounds(),
            initial_color=self.initial_color,
            rr_cycles=self.rr_cycles,
            pairing_engine=self.pairing_engine,
        )
        if not generated:
            raise ValueError("no pairings produced for the next round")
        self._pairings.extend(generated)
        self._round = next_round
        return generated

    def set_result(self, round_index: int, board: int, result: str) -> Pairing:
        if result not in VALID_RESULTS:
            raise ValueError(f"invalid result: {result}")
        for index, pairing in enumerate(self._pairings):
            if pairing.round_index == round_index and pairing.board == board:
                if pairing.is_bye and result not in {"bye", "zpb", "hpb"}:
                    raise ValueError("bye boards only accept a bye result")
                updated = Pairing(
                    pairing.round_index,
                    pairing.board,
                    pairing.white_id,
                    pairing.black_id,
                    result,
                    result_kind=result_kind_for(result),
                    manual=pairing.manual,
                )
                self._pairings[index] = updated
                return updated
        raise KeyError(f"no pairing for round {round_index} board {board}")

    def replace_round(
        self,
        round_index: int,
        pairings: tuple[Pairing, ...] | list[Pairing],
    ) -> tuple[Pairing, ...]:
        kept = [pairing for pairing in self._pairings if pairing.round_index != round_index]
        replaced = [pairing for pairing in pairings if pairing.round_index == round_index]
        if not replaced:
            raise ValueError("replacement round is empty")
        merged = sorted((*kept, *replaced), key=lambda item: (item.round_index, item.board))
        self._pairings = merged
        self._round = max(pairing.round_index for pairing in merged)
        return tuple(replaced)

    def standings(self) -> tuple[Standing, ...]:
        return standings(self.players, tuple(self._pairings))
