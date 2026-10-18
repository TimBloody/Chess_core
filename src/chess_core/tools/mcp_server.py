"""stdio MCP server that exposes Chess_core facts to Cursor agents."""

from __future__ import annotations

from chess_core.tools import agent_context as ctx


def _server():
    instructions = (
        "Chess_core project tools. Call project_brief or search_docs before exploring. "
        "Call list_modes / mode_details / mode_docs for rule descriptions "
        "(including education_branch modes) before guessing how pieces move. "
        "Call legal_moves/apply_move instead of guessing FEN or legality. "
        "Call where_to_change before editing so rules stay out of UI."
    )
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer("chess-core", instructions=instructions)
    except ImportError:
        pass
    try:
        from mcp.server import MCPServer

        return MCPServer("chess-core", instructions=instructions)
    except ImportError:
        from mcp.server.fastmcp import FastMCP

        return FastMCP("chess-core", instructions=instructions)


mcp = _server()


@mcp.tool()
def project_brief() -> dict:
    """Architecture, import rule, do-not-touch list, and common commands."""
    return ctx.project_brief()


@mcp.tool()
def search_docs(query: str, limit: int = 12) -> dict:
    """Search for_agent.me and docs/*.md for a keyword. Prefer this over reading the whole onboarding file."""
    return ctx.search_docs(query, limit=limit)


@mcp.tool()
def list_modes() -> dict:
    """Registered modes, overlays, and documented catalog (master + education_branch)."""
    return ctx.list_modes()


@mcp.tool()
def mode_details(mode_id: str) -> dict:
    """Live GameMode facts plus documented rules text for a mode id."""
    try:
        return ctx.mode_details(mode_id)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc), "mode_id": mode_id}


@mcp.tool()
def mode_docs(mode_id: str | None = None) -> dict:
    """Intended rules catalog. Omit mode_id for all modes including education_branch."""
    return ctx.mode_docs(mode_id)


@mcp.tool()
def legal_moves(
    mode_id: str,
    fen: str | None = None,
    square: str | None = None,
    limit: int = 80,
) -> dict:
    """Legal engine tokens for a mode. Omit fen for the start position. square is like e2."""
    try:
        return ctx.legal_moves(mode_id, fen=fen, square=square, limit=limit)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc), "mode_id": mode_id}


@mcp.tool()
def apply_move(mode_id: str, move: str, fen: str | None = None) -> dict:
    """Play a UCI/engine token (e2e4, P@e4, duck e2e4,e4e6) and return the new position."""
    try:
        return ctx.apply_move(mode_id, move, fen=fen)
    except (KeyError, ValueError) as exc:
        return {"error": str(exc), "mode_id": mode_id, "move": move}


@mcp.tool()
def where_to_change(task: str) -> dict:
    """Which layer should own a change: core, modes, app, infra, or ui."""
    return ctx.where_to_change(task)


@mcp.tool()
def related_tests(area: str) -> dict:
    """Test files that usually cover a feature area."""
    return ctx.related_tests(area)


@mcp.tool()
def check_layer_imports(path: str) -> dict:
    """Check a Python file against the ui -> app -> core import rule."""
    try:
        return ctx.check_layer_imports(path)
    except (OSError, SyntaxError) as exc:
        return {"error": str(exc), "path": path}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
