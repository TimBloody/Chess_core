"""Register built-in mode factories."""

from chess_core.core.registry import default_registry
from chess_core.modes import bughouse, chess, hand_and_brain, shogi


def register_builtin_modes() -> None:
    default_registry.register("chess", chess.classic_chess)
    default_registry.register("chess960", chess.chess960)
    default_registry.register("crazyhouse", chess.crazyhouse)
    default_registry.register("bughouse", bughouse.bughouse)
    default_registry.register("hand_and_brain", hand_and_brain.hand_and_brain)
    default_registry.register("giveaway", chess.giveaway)
    default_registry.register("minichess", chess.minichess)
    default_registry.register("cylindrical", chess.cylindrical_chess)
    default_registry.register("duck", chess.duck_chess)
    default_registry.register("shogi", shogi.shogi)
    default_registry.register("kyoto_shogi", shogi.kyoto_shogi)
    default_registry.register("dobutsu_shogi", shogi.dobutsu_shogi)
