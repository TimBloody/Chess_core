from chess_core.core.registry import default_registry
from chess_core.tools import agent_context as ctx


def test_list_modes_includes_builtins() -> None:
    listing = ctx.list_modes()
    assert "chess" in listing["registry"]
    assert "gobblet" in listing["registry"]
    layer_ids = {item["id"] for item in listing["layers"]}
    assert {"giveaway", "duck", "cylindrical"} <= layer_ids
    documented_ids = {item["id"] for item in listing["documented"]}
    assert "fairy" in documented_ids
    education_ids = {item["id"] for item in listing["education_branch"]}
    assert "three_check" in education_ids
    assert "gomoku" in education_ids


def test_mode_details_classic() -> None:
    details = ctx.mode_details("chess")
    assert details["files"] == 8
    assert details["ranks"] == 8
    assert details["royal_type"] == "king"
    assert details["checks_enabled"] is True
    assert "king" in details["piece_types"]
    assert details["live"] is True
    assert details["rules"]


def test_mode_details_fairytale_includes_file_rules() -> None:
    details = ctx.mode_details("fairytale")
    assert details["live"] is True
    assert details["move_resolver"] == "FairytaleFileResolver"
    assert "a/h" in details["rules"]


def test_mode_docs_education_without_live_factory() -> None:
    docs = ctx.mode_docs("three_check")
    assert docs["availability"] == "education_branch"
    assert "rules" in docs
    details = ctx.mode_details("three_check")
    assert details["live"] is False
    assert "rules" in details


def test_search_docs_finds_fairytale_catalog() -> None:
    payload = ctx.search_docs("FairytaleFileResolver")
    assert payload["hits"]
    text = " ".join(str(hit["text"]) for hit in payload["hits"])
    assert "a/h" in text or "файл" in text.lower()


def test_legal_moves_start_includes_e2e4() -> None:
    payload = ctx.legal_moves("chess", square="e2")
    assert payload["status"] == "ACTIVE"
    assert "e2e4" in payload["moves"]
    assert payload["side_to_move"] == "white"


def test_apply_move_updates_fen_and_side() -> None:
    after_white = ctx.apply_move("chess", "e2e4")
    assert after_white["side_to_move"] == "black"
    assert after_white["fen"] is not None
    assert "e2e4" in after_white["played"]
    after_black = ctx.apply_move("chess", "e7e5", fen=after_white["fen"])
    assert after_black["side_to_move"] == "white"
    assert after_black["status"] == "ACTIVE"


def test_illegal_move_returns_error() -> None:
    payload = ctx.apply_move("chess", "e2e5")
    assert "error" in payload


def test_where_to_change_routes_ui_and_core() -> None:
    assert ctx.where_to_change("подсветка клеток в виджете доски")["layer"] == "ui"
    assert ctx.where_to_change("легальные ходы слона на цилиндре")["layer"] == "core"


def test_related_tests_gobblet() -> None:
    payload = ctx.related_tests("gobblet")
    assert "tests/core/test_gobblet.py" in payload["tests"]


def test_check_layer_imports_core_is_clean() -> None:
    payload = ctx.check_layer_imports("src/chess_core/core/movegen.py")
    assert payload["layer"] == "core"
    assert payload["ok"] is True


def test_search_docs_finds_layer_rule() -> None:
    payload = ctx.search_docs("ui -> application -> core")
    files = {hit["file"] for hit in payload["hits"]}
    assert "for_agent.me" in files


def test_registry_not_polluted_after_list() -> None:
    ctx.list_modes()
    assert "chess" in default_registry.list_modes()
