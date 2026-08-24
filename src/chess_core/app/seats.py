"""Seat identifiers for 2-player and 4-player matches."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chess_core.core.piece import PieceSide


SPECTATOR = "spectator"

BOARD_A = "A"
BOARD_B = "B"
BOARD_MAIN = "main"


class SeatDuty(Enum):
    MOVER = auto()
    BRAIN = auto()
    HAND = auto()


@dataclass(frozen=True, slots=True)
class SeatSpec:
    seat_id: str
    side: PieceSide
    board_id: str
    duty: SeatDuty
    label: str


SINGLE_SEATS: tuple[SeatSpec, ...] = (
    SeatSpec("white", PieceSide.WHITE, BOARD_MAIN, SeatDuty.MOVER, "Белые"),
    SeatSpec("black", PieceSide.BLACK, BOARD_MAIN, SeatDuty.MOVER, "Чёрные"),
)

BUGHOUSE_SEATS: tuple[SeatSpec, ...] = (
    SeatSpec("a_white", PieceSide.WHITE, BOARD_A, SeatDuty.MOVER, "Доска A · белые"),
    SeatSpec("a_black", PieceSide.BLACK, BOARD_A, SeatDuty.MOVER, "Доска A · чёрные"),
    SeatSpec("b_white", PieceSide.WHITE, BOARD_B, SeatDuty.MOVER, "Доска B · белые"),
    SeatSpec("b_black", PieceSide.BLACK, BOARD_B, SeatDuty.MOVER, "Доска B · чёрные"),
)

HAND_AND_BRAIN_SEATS: tuple[SeatSpec, ...] = (
    SeatSpec("white_brain", PieceSide.WHITE, BOARD_MAIN, SeatDuty.BRAIN, "Белые · Brain"),
    SeatSpec("white_hand", PieceSide.WHITE, BOARD_MAIN, SeatDuty.HAND, "Белые · Hand"),
    SeatSpec("black_brain", PieceSide.BLACK, BOARD_MAIN, SeatDuty.BRAIN, "Чёрные · Brain"),
    SeatSpec("black_hand", PieceSide.BLACK, BOARD_MAIN, SeatDuty.HAND, "Чёрные · Hand"),
)

BUGHOUSE_PARTNER = {
    "a_white": "b_black",
    "a_black": "b_white",
    "b_white": "a_black",
    "b_black": "a_white",
}

BUGHOUSE_TEAMS = {
    "a_white": "team_light",
    "b_black": "team_light",
    "a_black": "team_dark",
    "b_white": "team_dark",
}


def seats_for_match_kind(kind: str) -> tuple[SeatSpec, ...]:
    if kind == "bughouse":
        return BUGHOUSE_SEATS
    if kind == "hand_and_brain":
        return HAND_AND_BRAIN_SEATS
    return SINGLE_SEATS


def spec_by_id(kind: str, seat_id: str) -> SeatSpec | None:
    if seat_id == SPECTATOR:
        return None
    for spec in seats_for_match_kind(kind):
        if spec.seat_id == seat_id:
            return spec
    return None


def partner_board(board_id: str) -> str:
    if board_id == BOARD_A:
        return BOARD_B
    if board_id == BOARD_B:
        return BOARD_A
    return BOARD_MAIN


def partner_side(side: PieceSide) -> PieceSide:
    return PieceSide.BLACK if side is PieceSide.WHITE else PieceSide.WHITE
