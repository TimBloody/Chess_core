"""Application service for tournament draws."""

from __future__ import annotations

import random

from chess_core.app.tournament.models import (
    VALID_RESULTS,
    Pairing,
    PairingSystem,
    Player,
    Standing,
)
from chess_core.app.tournament.pairings import all_round_robin_rounds, pair_round, standings


class TournamentService:
    def __init__(
        self,
        system: PairingSystem,
        players: tuple[Player, ...] | list[Player],
        *,
        swiss_rounds: int = 0,
        seed: int | None = None,
    ) -> None:
        self.system = system
        self.players = tuple(players)
        if len(self.players) < 2:
            raise ValueError("tournament needs at least two players")
        self.swiss_rounds = swiss_rounds
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
            return n if n % 2 else n - 1
        if self.system is PairingSystem.SWISS:
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
        if self.system is PairingSystem.ROUND_ROBIN and self._round == 0:
            generated = [pairing for round_games in all_round_robin_rounds(self.players) for pairing in round_games]
            self._pairings.extend(generated)
            self._round = self.expected_rounds()
            return tuple(generated)
        generated = pair_round(
            self.system,
            self.players,
            tuple(self._pairings),
            round_index=next_round,
            rng=self._rng,
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
                if pairing.is_bye and result != "bye":
                    raise ValueError("bye boards only accept a bye result")
                updated = Pairing(
                    pairing.round_index,
                    pairing.board,
                    pairing.white_id,
                    pairing.black_id,
                    result,
                )
                self._pairings[index] = updated
                return updated
        raise KeyError(f"no pairing for round {round_index} board {board}")

    def standings(self) -> tuple[Standing, ...]:
        return standings(self.players, tuple(self._pairings))
