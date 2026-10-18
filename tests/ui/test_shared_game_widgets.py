"""Tests for shared game widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from chess_core.app.clock import GameClockService
from chess_core.app.engine import EngineEvaluation
from chess_core.core.piece import Piece, PieceSide, PieceTypeId
from chess_core.core.state import HandsState
from chess_core.core.time_control import TimeControlConfig, TimeControlKind
from chess_core.modes import register_builtin_modes
from chess_core.modes.shogi import dobutsu_shogi, kyoto_shogi
from chess_core.ui.assets_loader import AssetsLoader
from chess_core.ui.local_game import LocalGameWidget
from chess_core.ui.piece_keys import drop_flip_map, piece_asset_key, should_rotate_facing_art
from chess_core.ui.widgets.evaluation_bar import EvaluationBarWidget
from chess_core.ui.widgets.game_clock import GameClockWidget
from chess_core.ui.widgets.move_list import MoveListWidget
from chess_core.ui.widgets.pocket_widget import PocketWidget
from chess_core.ui.widgets.time_control_dialog import TimeControlDialog

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_move_list_emits_revision() -> None:
    _app()
    widget = MoveListWidget()
    widget.set_moves(["1. e4  e5"], live_revision=1, view_revision=1)
    assert widget.rowCount() == 1


def test_move_list_click_uses_ply_revision_not_row_index() -> None:
    from chess_core.app.game_record import MoveLogLine

    _app()
    widget = MoveListWidget()
    lines = [
        MoveLogLine(1, white="e4", black="e5", white_revision=1, black_revision=2),
        MoveLogLine(2, white="Nf3", black="Nc6", white_revision=3, black_revision=4),
    ]
    widget.set_moves(lines, live_revision=4, view_revision=4)
    assert widget.rowCount() == 2
    clicked: list[int] = []
    widget.revision_selected.connect(clicked.append)
    widget._on_cell_clicked(0, 0)
    widget._on_cell_clicked(0, 1)
    widget._on_cell_clicked(0, 2)
    widget._on_cell_clicked(1, 0)
    widget._on_cell_clicked(1, 1)
    widget._on_cell_clicked(1, 2)
    assert clicked == [2, 1, 2, 4, 3, 4]
    current = widget.currentItem()
    assert current is not None
    assert current.data(256) == 4


def test_clock_widget_formats_snapshot() -> None:
    _app()
    widget = GameClockWidget()
    service = GameClockService(TimeControlConfig.sudden_death(5), _Clock())
    widget.set_snapshot(service.snapshot())
    assert ":" in widget._white.text()
    assert "Контроль 5+0" in widget._mode.text()
    style = widget.black_clock.styleSheet().lower()
    assert "#f5f5f5" in style
    assert "playerclockwidget qlabel" in style


def test_clock_widget_click_emits_only_when_settings_enabled() -> None:
    _app()
    widget = GameClockWidget()
    clicks: list[int] = []
    widget.clicked.connect(lambda: clicks.append(1))
    QTest.mouseClick(widget.white_clock, Qt.MouseButton.LeftButton)
    assert clicks == []
    widget.set_settings_enabled(True)
    QTest.mouseClick(widget.white_clock, Qt.MouseButton.LeftButton)
    assert clicks == [1]
    QTest.mouseDClick(widget.black_clock, Qt.MouseButton.LeftButton)
    assert clicks[-1] == 1
    assert len(clicks) >= 2


def test_time_control_dialog_builds_bronstein_and_byoyomi() -> None:
    _app()
    dialog = TimeControlDialog(TimeControlConfig.blitz())
    assert dialog.config().kind is TimeControlKind.FISCHER
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData(TimeControlKind.BRONSTEIN))
    dialog.main_minutes.setValue(10)
    dialog.extra_seconds.setValue(5)
    bronstein = dialog.config()
    assert bronstein.kind is TimeControlKind.BRONSTEIN
    assert bronstein.main_minutes == 10
    assert bronstein.extra_seconds == 5
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData(TimeControlKind.BYOYOMI))
    dialog.main_minutes.setValue(15)
    dialog.extra_seconds.setValue(30)
    byoyomi = dialog.config()
    assert byoyomi.kind is TimeControlKind.BYOYOMI
    assert byoyomi.initial_ms == (900_000, 900_000)
    assert byoyomi.byoyomi_period_ms == 30_000


def test_time_control_dialog_none_disables_fields() -> None:
    _app()
    dialog = TimeControlDialog(TimeControlConfig.blitz())
    dialog.kind_combo.setCurrentIndex(dialog.kind_combo.findData(TimeControlKind.NONE))
    assert not dialog.main_minutes.isEnabled()
    assert not dialog.extra_seconds.isEnabled()
    assert dialog.config() == TimeControlConfig.none()


def test_local_game_can_change_clock_after_start() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    assert widget.clock_widget.settings_enabled
    chosen = TimeControlConfig.from_parts(
        TimeControlKind.FISCHER,
        main_minutes=5,
        extra_seconds=0,
    )
    assert widget.apply_time_control(chosen)
    assert widget._clock_service is not None
    snapshot = widget._clock_service.snapshot()
    assert snapshot.white_remaining_ms == 300_000
    assert "Фишер 5+0" in widget.clock_widget._mode.text()
    widget._clock_service.on_move_committed(PieceSide.WHITE, 0)
    widget._sync_clock_with_game()
    assert widget.clock_widget.settings_enabled
    assert widget.apply_time_control(TimeControlConfig.blitz())
    widget.close()


def test_local_game_load_position_resets_clock_settings() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.notation import parse_fen
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    assert widget._clock_service is not None
    widget._clock_service.on_move_committed(PieceSide.WHITE, 0)
    widget._sync_clock_with_game()
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
    widget.load_position(parse_fen(fen, widget.service.mode))
    assert widget.clock_widget.settings_enabled
    assert widget.apply_time_control(
        TimeControlConfig.from_parts(TimeControlKind.FISCHER, main_minutes=10, extra_seconds=0)
    )
    assert widget._clock_service is not None
    assert widget._clock_service.snapshot().white_remaining_ms == 600_000
    assert not widget._clock_service.has_started
    widget.close()


def test_local_game_can_disable_clock_after_move_and_hides_timer() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget.show()
    assert widget._clock_service is not None
    widget._clock_service.on_move_committed(PieceSide.WHITE, 0)
    widget._sync_clock_with_game()
    assert widget.clock_widget.isVisible()
    assert widget.apply_time_control(TimeControlConfig.none())
    assert not widget.clock_widget.isVisible()
    assert widget.clock_off_button.isVisible()
    assert widget.apply_time_control(TimeControlConfig.blitz())
    assert widget.clock_widget.isVisible()
    assert not widget.clock_off_button.isVisible()
    widget.close()


def test_local_game_clock_double_click_opens_time_control_dialog(monkeypatch) -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    chosen = TimeControlConfig.from_parts(
        TimeControlKind.BRONSTEIN,
        main_minutes=10,
        extra_seconds=5,
    )
    opened: list[TimeControlConfig] = []

    class _Dialog:
        def __init__(self, initial: TimeControlConfig, parent=None) -> None:
            opened.append(initial)

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def config(self) -> TimeControlConfig:
            return chosen

    monkeypatch.setattr("chess_core.ui.local_game.TimeControlDialog", _Dialog)
    assert widget.clock_widget.settings_enabled
    QTest.mouseDClick(widget.clock_widget.white_clock, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert opened
    assert widget._time_control == chosen
    assert "Бронштейн 10+5" in widget.clock_widget._mode.text()
    widget.close()


def test_evaluation_bar_shows_cp() -> None:
    _app()
    widget = EvaluationBarWidget()
    widget.set_evaluation(EngineEvaluation(score_cp=35, mate_in=None, pv=("e2e4",)))
    assert "+0.3" in widget._bar.text()
    assert "e2e4" not in widget._bar.text()


def test_pocket_omits_zero_counts_and_shows_only_owned_types() -> None:
    _app()
    hands = HandsState()
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("silver"), PieceSide.WHITE))
    widget = PocketWidget(PieceSide.WHITE)
    widget.set_hands(
        hands,
        PieceSide.WHITE,
        types=("pawn", "lance", "knight", "silver", "gold", "bishop", "rook"),
        asset_family="shogi",
        grid=True,
    )
    assert widget.visible_types == ("pawn", "silver")
    assert widget.is_grid
    assert widget._stacks[0].count == 2
    assert widget._stacks[0].piece_key == "0FU"


def test_dobutsu_piece_keys_use_animal_svgs() -> None:
    mode = dobutsu_shogi()
    state = mode.initial_state()
    white_lion = state.board_state.piece_at(1)
    black_lion = state.board_state.piece_at(10)
    white_key = piece_asset_key(white_lion, mode.asset_family)
    black_key = piece_asset_key(black_lion, mode.asset_family)
    assert white_key == "dobutsu/lion@w"
    assert black_key == "dobutsu/lion@b"
    assets = AssetsLoader()
    assert assets.piece_path(white_key).name == "lion.svg"
    assert assets.piece_path("dobutsu/chick@w").name == "chick.svg"
    assert assets.piece_path("dobutsu/giraffe@b").name == "giraffe.svg"


def test_dobutsu_local_game_does_not_use_chess_piece_keys() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "dobutsu_shogi")
    assert widget.board.position[1] == "dobutsu/lion@w"
    assert widget.board.position[10] == "dobutsu/lion@b"
    assert widget.board.position[4] == "dobutsu/chick@w"
    assert widget.white_pocket.is_grid
    widget.close()


def test_pocket_right_click_flips_kyoto_face() -> None:
    _app()
    hands = HandsState()
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("pawn"), PieceSide.WHITE))
    widget = PocketWidget(PieceSide.WHITE)
    widget.set_hands(
        hands,
        PieceSide.WHITE,
        types=("pawn", "lance", "knight", "silver", "gold", "bishop", "rook"),
        asset_family="shogi",
        grid=True,
        flip_map=drop_flip_map(kyoto_shogi()),
    )
    widget.set_selected("pawn")
    assert widget.selected_face() == "pawn"
    widget._flip_stack("pawn")
    assert widget.selected_face() == "rook"
    widget._flip_stack("pawn")
    assert widget.selected_face() == "pawn"


def test_facing_art_rotates_so_near_side_looks_like_own_pieces() -> None:
    assert not should_rotate_facing_art("dobutsu/chick@w", facing_black=False)
    assert should_rotate_facing_art("dobutsu/chick@b", facing_black=False)
    assert should_rotate_facing_art("dobutsu/lion@w", facing_black=True)
    assert not should_rotate_facing_art("dobutsu/lion@b", facing_black=True)
    assert not should_rotate_facing_art("0FU", facing_black=False)
    assert not should_rotate_facing_art("1OU", facing_black=False)
    assert should_rotate_facing_art("0FU", facing_black=True)
    assert should_rotate_facing_art("1OU", facing_black=True)
    assert not should_rotate_facing_art("wP", facing_black=True)
    assert not should_rotate_facing_art("bN", facing_black=True)


def test_pocket_rotates_komadai_with_board_orientation() -> None:
    _app()
    hands = HandsState()
    hands.add(PieceSide.WHITE, Piece(PieceTypeId("chick"), PieceSide.WHITE))
    hands.add(PieceSide.BLACK, Piece(PieceTypeId("chick"), PieceSide.BLACK))
    white = PocketWidget(PieceSide.WHITE)
    black = PocketWidget(PieceSide.BLACK)
    types = ("chick", "giraffe", "elephant", "hen")
    white.set_hands(hands, PieceSide.WHITE, types=types, asset_family="dobutsu")
    black.set_hands(hands, PieceSide.BLACK, types=types, asset_family="dobutsu")
    assert not white.should_rotate_key("dobutsu/chick@w")
    assert black.should_rotate_key("dobutsu/chick@b")
    white.set_hands(
        hands, PieceSide.WHITE, types=types, asset_family="dobutsu", facing_black=True
    )
    black.set_hands(
        hands, PieceSide.BLACK, types=types, asset_family="dobutsu", facing_black=True
    )
    assert white.facing_black
    assert white.should_rotate_key("dobutsu/chick@w")
    assert not black.should_rotate_key("dobutsu/chick@b")


def test_local_shogi_flip_turns_komadai_to_face_the_viewer() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry
    from chess_core.ui.widgets.board_widget import BoardOrientation

    widget = LocalGameWidget(default_registry.get, "shogi", discovered=[])
    assert widget.board.orientation is BoardOrientation.WHITE
    assert not widget.white_pocket.facing_black
    assert not widget.white_pocket.should_rotate_key("0FU")
    assert not widget.black_pocket.should_rotate_key("1FU")
    assert not widget.board._should_rotate_piece("0FU")
    widget.flip_board()
    assert widget.board.orientation is BoardOrientation.BLACK
    assert widget.white_pocket.facing_black
    assert widget.black_pocket.facing_black
    assert widget.white_pocket.should_rotate_key("0FU")
    assert widget.black_pocket.should_rotate_key("1FU")
    assert widget.board._should_rotate_piece("0FU")
    assert widget.board._should_rotate_piece("1OU")
    widget.close()

    dobutsu = LocalGameWidget(default_registry.get, "dobutsu_shogi", discovered=[])
    assert not dobutsu.white_pocket.should_rotate_key("dobutsu/chick@w")
    assert dobutsu.black_pocket.should_rotate_key("dobutsu/chick@b")
    dobutsu.flip_board()
    assert dobutsu.white_pocket.should_rotate_key("dobutsu/chick@w")
    assert not dobutsu.black_pocket.should_rotate_key("dobutsu/chick@b")
    assert dobutsu.board._should_rotate_piece("dobutsu/lion@w")
    assert not dobutsu.board._should_rotate_piece("dobutsu/lion@b")
    dobutsu.close()


def test_duck_blocker_is_drawn_on_the_board() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.board import Square
    from chess_core.core.move import MoveAction, PlaceBlockerAction, Turn
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "duck", discovered=[])
    turn = Turn(
        PieceSide.WHITE,
        [
            MoveAction(Square(4, 1), Square(4, 3)),
            PlaceBlockerAction(Square(4, 2)),
        ],
    )
    widget.service.play_turn(turn)
    widget._refresh()
    assert widget.board.position.get(20) == "blocker"
    assert piece_asset_key(
        widget.service.state.board_state.piece_at(20),
        "chess",
    ) == "blocker"
    widget.close()


def test_reversi_uses_checker_discs_not_pawns() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    disc = PieceTypeId("disc")
    assert piece_asset_key(Piece(disc, PieceSide.WHITE), "chess") == "wdisc"
    assert piece_asset_key(Piece(disc, PieceSide.BLACK), "chess") == "bdisc"
    assets = AssetsLoader()
    assert assets.piece_path("wdisc").name == "wdisc.svg"
    assert assets.piece_path("bdisc").name == "bdisc.svg"
    widget = LocalGameWidget(default_registry.get, "reversi", discovered=[])
    assert widget.board.position[28] == "wdisc"
    assert widget.board.position[27] == "bdisc"
    assert "wP" not in widget.board.position.values()
    widget.close()


def test_corners_and_draughts_use_checker_discs_not_pawns() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry

    man = PieceTypeId("man")
    kingman = PieceTypeId("kingman")
    assert piece_asset_key(Piece(man, PieceSide.WHITE), "chess") == "wdisc"
    assert piece_asset_key(Piece(man, PieceSide.BLACK), "chess") == "bdisc"
    assert piece_asset_key(Piece(kingman, PieceSide.WHITE), "chess") == "wkingman"
    assert piece_asset_key(Piece(kingman, PieceSide.BLACK), "chess") == "bkingman"
    assets = AssetsLoader()
    assert assets.piece_path("wkingman").name == "wkingman.svg"
    assert assets.piece_path("bkingman").name == "bkingman.svg"

    corners = LocalGameWidget(default_registry.get, "corners", discovered=[])
    assert corners.board.position[0] == "wdisc"
    assert corners.board.position[63] == "bdisc"
    assert "wP" not in corners.board.position.values()
    assert "bP" not in corners.board.position.values()
    corners.close()

    draughts = LocalGameWidget(default_registry.get, "draughts", discovered=[])
    assert draughts.board.position[0] == "wdisc"
    assert draughts.board.position[61] == "bdisc"
    assert "wP" not in draughts.board.position.values()
    assert "wQ" not in draughts.board.position.values()
    draughts.close()


def test_local_game_notation_click_opens_full_move_not_halfmove() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.board import Square
    from chess_core.core.move import MoveAction, Turn
    from chess_core.core.piece import PieceSide
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget.service.play_turn(Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]))
    widget.service.play_turn(Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))]))
    widget.service.play_turn(Turn(PieceSide.WHITE, [MoveAction(Square(6, 0), Square(5, 2))]))
    widget.service.play_turn(Turn(PieceSide.BLACK, [MoveAction(Square(1, 7), Square(2, 5))]))
    widget._refresh()
    assert widget.service.record.live_revision == 4
    assert len(widget.service.move_log_lines) == 2

    widget._on_revision_selected(2)
    assert widget.service.record.view_revision == 2
    assert 21 not in widget.board.position
    assert widget.board.position.get(28) == "wP"

    widget._on_revision_selected(4)
    assert widget.service.record.view_revision == 4
    assert widget.board.position.get(21) == "wN"
    assert widget.board.position.get(42) == "bN"

    widget.move_list._on_cell_clicked(1, 0)
    assert widget.service.record.view_revision == 4
    widget.move_list._on_cell_clicked(1, 1)
    assert widget.service.record.view_revision == 3
    assert widget.board.position.get(21) == "wN"
    assert 42 not in widget.board.position
    widget.close()


def test_last_move_highlight_follows_viewed_revision() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.board import Square
    from chess_core.core.move import MoveAction, Turn
    from chess_core.core.piece import PieceSide
    from chess_core.core.registry import default_registry

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    widget.service.play_turn(Turn(PieceSide.WHITE, [MoveAction(Square(4, 1), Square(4, 3))]))
    widget.service.play_turn(Turn(PieceSide.BLACK, [MoveAction(Square(4, 6), Square(4, 4))]))
    widget.service.play_turn(Turn(PieceSide.WHITE, [MoveAction(Square(6, 0), Square(5, 2))]))
    widget._refresh()
    assert widget.board._last_move_squares == {6, 21}

    widget._on_revision_selected(1)
    assert widget.service.record.view_revision == 1
    assert widget.board._last_move_squares == {12, 28}

    widget._on_revision_selected(0)
    assert widget.board._last_move_squares == set()

    widget._on_revision_selected(2)
    assert widget.board._last_move_squares == {52, 36}
    widget.close()


def test_mate_winner_text_stays_correct_when_browsing_archive() -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry
    from chess_core.tools.classical_demo import parse_move

    widget = LocalGameWidget(default_registry.get, "chess", discovered=[])
    for value in ("e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"):
        widget.service.play(parse_move(value))
    widget._refresh()
    assert "Победили белые" in widget.status.text()

    widget._on_revision_selected(1)
    assert not widget.service.is_live
    assert "Победили белые" in widget.status.text()
    assert "Победили чёрные" not in widget.status.text()
    assert "[архив]" in widget.status.text()

    widget._on_revision_selected(2)
    assert "Победили белые" in widget.status.text()
    assert "Победили чёрные" not in widget.status.text()
    widget.close()


def test_local_game_copy_and_save_transcript_for_any_mode(tmp_path) -> None:
    _app()
    register_builtin_modes()
    from chess_core.core.registry import default_registry
    from chess_core.modes.gobblet_rules import GOBBLET_MEDIUM
    from chess_core.core.board import Square
    from chess_core.core.move import DropAction, Turn
    from chess_core.core.piece import PieceSide

    widget = LocalGameWidget(default_registry.get, "gobblet", discovered=[])
    widget._refresh()
    assert not widget.copy_record_button.isEnabled()
    widget.service.play_turn(
        Turn(PieceSide.WHITE, [DropAction(GOBBLET_MEDIUM, Square(0, 0))])
    )
    widget._refresh()
    assert widget.copy_record_button.isEnabled()
    text = widget.copy_transcript()
    assert text is not None
    assert '[Mode "gobblet"]' in text
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    assert '[Mode "gobblet"]' in clipboard.text()
    target = tmp_path / "gobblet.txt"
    assert widget.save_transcript(target)
    saved = target.read_text(encoding="utf-8")
    assert saved == text
    database = tmp_path / "games.pgn"
    assert widget.add_transcript_to_database(database)
    raw = database.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    assert widget.add_transcript_to_database(database)
    from chess_core.core.pgn import parse_pgn
    from chess_core.infra.storage.pgn_files import decode_pgn_bytes

    assert len(parse_pgn(decode_pgn_bytes(database.read_bytes()))) == 1
    widget.close()


class _Clock:
    def now_ms(self) -> int:
        return 0
