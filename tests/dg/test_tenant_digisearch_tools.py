"""Dedicated per-index digisearch tools from the tenant corpus map (DIG-3269)."""

from __future__ import annotations

import json
from unittest.mock import patch

from digigraph.corpus_routing import load_tenant_corpus_map, resolve_corpus_override
from digigraph.graph import research
from digigraph.orchestration.registry import ToolContext

_MAP = {
    "occ": {
        "digisearchIndex": "occ_help",
        "digisearchTools": {
            "digisearch_occ_help": {"index": "occ_help", "description": "help docs"},
            "digisearch_zammad_tickets": {"index": "occ-tickets", "description": "tickets"},
            "digisearch_fetch_all": {"index": "x", "description": "reserved"},
            "digisearch_bad": {"index": "a,b", "description": "fan-out not allowed"},
        },
    }
}


def test_map_parses_dedicated_tools() -> None:
    table = load_tenant_corpus_map(json.dumps(_MAP))
    o = resolve_corpus_override(tenant_slug="occ", corpus_map=table)
    assert o.digisearch_tools == {
        "digisearch_occ_help": {"index": "occ_help", "description": "help docs"},
        "digisearch_zammad_tickets": {"index": "occ-tickets", "description": "tickets"},
    }


def _ctx(allowed=None) -> ToolContext:
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="occ_help",
        index_config={},
        state={},
        allowed_tool_names=allowed,
    )


def test_each_tool_is_bound_to_its_own_index() -> None:
    seen = []

    def fake(args, ctx):
        seen.append((ctx.index_name, args))
        return {"content": "x", "results": [], "rag_sources": []}

    with patch("digigraph.orchestration.digisearch_tools._handle_digisearch", fake):
        research._run_tenant_search_tool(
            "occ-tickets", {"query": "q", "index_name": "digithings_docs"}, _ctx()
        )
    assert seen == [("occ-tickets", {"query": "q"})]


def test_tool_respects_disabled_digisearch() -> None:
    out = research._run_tenant_search_tool("occ_help", {"query": "q"}, _ctx(frozenset({"todo"})))
    assert isinstance(out, str) and "not allowed" in out


def test_schema_has_no_index_argument() -> None:
    s = research._tenant_search_schema("digisearch_occ_help", {"index": "i", "description": "d"})
    assert set(s["function"]["parameters"]["properties"]) == {"query", "top_k"}


# --- Ticket search is an ADDITION next to help search (#6302 review) ---
_SLUG, _TIX = "occ", "occ-tickets"
_HELP = _MAP[_SLUG]["digisearchIndex"]  # the help index; the live map must agree
# The five live ticket MCP tools pass through untouched; generic stand-in names.
_LIVE = ("search_tickets", "list_tickets", "get_ticket", "customer_history", "ticket_report")
_LIVE_TOOLS = tuple(f"tickets_mcp__{n}" for n in _LIVE)


def _ticket_tool(o) -> str:
    """The dedicated tool the live map binds to the ticket collection."""
    return next(n for n, s in (o.digisearch_tools or {}).items() if s["index"] == _TIX)


def _fn(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name}}


def _names(tools: list) -> list[str]:
    return [research._tool_def_name(t) for t in tools]


def _live_override():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    raw = tomllib.loads((root / "apps/digithings-stack-cloudflare/wrangler.toml").read_text())
    table = load_tenant_corpus_map(raw["vars"]["DIGI_TENANT_CORPUS_MAP"])
    return resolve_corpus_override(tenant_slug=_SLUG, corpus_map=table)


def test_live_tool_set_keeps_help_search_and_adds_ticket_search() -> None:
    o = _live_override()
    assert o.digisearch_index == _HELP
    base = [_fn("digisearch"), _fn("digisearch_fetch_all"), _fn("digivault_search_notes")]
    base += [_fn(n) for n in _LIVE_TOOLS]
    tools, bound = research._apply_tenant_search_tools(base, o.digisearch_tools, set(), _HELP)
    names = set(_names(tools))
    _TIX_TOOL = _ticket_tool(o)
    assert _TIX_TOOL.startswith("digisearch_") and _TIX_TOOL.endswith("_tickets")
    for expected in ("digisearch", "digisearch_fetch_all", _TIX_TOOL, *_LIVE_TOOLS):
        assert expected in names, expected
    assert bound[_TIX_TOOL]["index"] == _TIX


def test_dedicated_tools_covering_the_tenant_index_still_replace_generic_search() -> None:
    table = load_tenant_corpus_map(json.dumps(_MAP))
    o = resolve_corpus_override(tenant_slug=_SLUG, corpus_map=table)
    base = [_fn("digisearch"), _fn("digisearch_fetch_all"), _fn("todo")]
    tools, _ = research._apply_tenant_search_tools(base, o.digisearch_tools, set(), _HELP)
    names = _names(tools)
    assert "digisearch" not in names and "digisearch_fetch_all" not in names
    assert {f"digisearch_{_HELP}", _ticket_tool(o), "todo"} <= set(names)


def test_no_generic_search_means_no_dedicated_tools() -> None:
    o = _live_override()
    tools, bound = research._apply_tenant_search_tools(
        [_fn("todo")], o.digisearch_tools, set(), _HELP
    )
    assert _names(tools) == ["todo"] and bound == {}


def test_session_disabled_dedicated_tool_is_not_offered() -> None:
    o = _live_override()
    base = [_fn("digisearch"), _fn("digisearch_fetch_all")]
    _TIX_TOOL = _ticket_tool(o)
    tools, bound = research._apply_tenant_search_tools(base, o.digisearch_tools, {_TIX_TOOL}, _HELP)
    assert _TIX_TOOL not in _names(tools) and "digisearch" in _names(tools)
    assert bound == {}
