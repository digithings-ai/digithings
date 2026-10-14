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
