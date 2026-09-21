from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server


def _tool_names(server) -> set[str]:
    # Prefer a public accessor; fall back to FastMCP's internal manager across versions.
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


@pytest.mark.unit
def test_data_tools_registered():
    names = _tool_names(create_mcp_server())
    assert "digiquant_get_price_technicals" in names, f"missing data tool; got {sorted(names)}"
    assert "digiquant_get_macro_series" in names, f"missing data tool; got {sorted(names)}"


@pytest.mark.unit
def test_query_research_tool_registered():
    """#4436: external agents search research output + the paper book by filters."""
    names = _tool_names(create_mcp_server())
    assert "digiquant_query_research" in names, f"missing query_research tool; got {sorted(names)}"


@pytest.mark.unit
def test_query_data_tool_removed():
    """The generic raw-table reader was folded into query_research (#4436)."""
    names = _tool_names(create_mcp_server())
    assert "digiquant_query_data" not in names


@pytest.mark.unit
def test_query_research_documents_house_scope():
    """The MCP wrapper reads the house book; documents resolve through house scope."""
    server = create_mcp_server()
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    qr = next(t for t in tools if t.name == "digiquant_query_research")
    assert "r2" in qr.description.lower()
    assert "include_prior" in qr.description.lower()


def _tool_fn(server, name: str):
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    tool = next(t for t in tools if t.name == name)
    return getattr(tool, "fn", None) or tool


class _StubSupabaseConfig:
    @classmethod
    def from_env(cls) -> "_StubSupabaseConfig":
        return cls()


@pytest.mark.unit
def test_query_research_forwards_phase_as_retrieval_phase(monkeypatch):
    """#4467 F2: the wrapper must forward ``phase`` as ``retrieval_phase``.

    The external read-scope tool could never request a blinded view — it ran
    every search as ``research_edit``, returning ``beliefs`` and the digest.
    """
    import digiquant.dashboard.research_retrieval.queries as queries_mod
    import digiquant.research.supabase_io as io_mod

    captured: dict[str, object] = {}

    def _fake_search_research(**kwargs):
        captured.update(kwargs)
        return {"row_count": 0, "rows": []}

    monkeypatch.setattr(queries_mod, "search_research", _fake_search_research)
    monkeypatch.setattr(io_mod, "SupabaseConfig", _StubSupabaseConfig)
    monkeypatch.setattr(io_mod, "build_client", lambda _cfg: object())

    fn = _tool_fn(create_mcp_server(scope="read"), "digiquant_query_research")

    out = json.loads(fn(dataset="documents", phase="h5_analyst"))
    assert "error" not in out, out
    assert captured["retrieval_phase"] == "h5_analyst"

    # D2 (owner directive): the external read-scope surface is blinded by
    # default for the document/digest datasets ...
    captured.clear()
    fn(dataset="documents")
    assert captured["retrieval_phase"] == "h5_analyst"

    captured.clear()
    fn(dataset="daily_snapshots")
    assert captured["retrieval_phase"] == "h5_analyst"

    # ... while the book datasets keep the operator default.
    captured.clear()
    fn(dataset="positions")
    assert captured["retrieval_phase"] == "research_edit"
