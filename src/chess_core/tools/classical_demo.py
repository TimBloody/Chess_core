"""Small headless classical-chess runner using coordinate moves."""

from __future__ import annotations

import argparse

from chess_core.app.game import LocalGameService
from chess_core.core.board import Square
from chess_core.core.move import MoveAction
from chess_core.core.notation import to_fen
from chess_core.core.piece import PieceTypeId
from chess_core.modes.chess import classic_chess

_PROMOTIONS = {"q": "queen", "r": "rook", "b": "bishop", "n": "knight"}


def parse_move(value: str) -> MoveAction:
    value = value.strip().lower()
    if len(value) not in {4, 5}:
        raise ValueError("move must look like e2e4 or a7a8q")

    def square(token: str) -> Square:
        if token[0] not in "abcdefgh" or token[1] not in "12345678":
            raise ValueError(f"invalid square: {token}")
        return Square(ord(token[0]) - ord("a"), int(token[1]) - 1)

    promotion = None
    if len(value) == 5:
        try:
            promotion = PieceTypeId(_PROMOTIONS[value[4]])
        except KeyError as exc:
            raise ValueError("promotion must be q, r, b, or n") from exc
    return MoveAction(square(value[:2]), square(value[2:4]), promotion)


def run_moves(values: list[str]) -> LocalGameService:
    game = LocalGameService(classic_chess())
    for value in values:
        game.play(parse_move(value))
    return game


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("moves", nargs="*", help="coordinate moves, e.g. e2e4")
    args = parser.parse_args()
    values = args.moves or [
        "e2e4",
        "e7e5",
        "f1c4",
        "b8c6",
        "d1h5",
        "g8f6",
        "h5f7",
    ]
    try:
        game = run_moves(values)
    except ValueError as exc:
        parser.error(str(exc))
    print(to_fen(game.state))
    print(game.status().name.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
