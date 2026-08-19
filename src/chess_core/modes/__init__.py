"""Register built-in mode factories."""

from chess_core.core.registry import default_registry
from chess_core.modes import chess, shogi


def register_builtin_modes() -> None:
    default_registry.register("chess", chess.classic_chess)
    default_registry.register("chess960", chess.chess960)
    default_registry.register("crazyhouse", chess.crazyhouse)
    default_registry.register("giveaway", chess.giveaway)
    default_registry.register("minichess", chess.minichess)
    default_registry.register("cylindrical", chess.cylindrical_chess)
    default_registry.register("duck", chess.duck_chess)
    default_registry.register("two_move", chess.two_move_chess)
    default_registry.register("fairytale", chess.fairytale_chess)
    default_registry.register("three_check", chess.three_check_chess)
    default_registry.register("king_of_the_hill", chess.king_of_the_hill)
    default_registry.register(
        "three_check_king_of_the_hill", chess.three_check_king_of_the_hill
    )
    default_registry.register("shogi", shogi.shogi)
    default_registry.register("minishogi", shogi.minishogi)
    default_registry.register("kyoto_shogi", shogi.kyoto_shogi)
    default_registry.register("dobutsu_shogi", shogi.dobutsu_shogi)
