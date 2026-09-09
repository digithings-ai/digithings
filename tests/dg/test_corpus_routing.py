"""Unit tests for digigraph per-tenant corpus routing."""

from __future__ import annotations

import pytest
from digigraph.corpus_routing import (
    TenantCorpusMapError,
    TenantCorpusOverride,
    load_tenant_corpus_map,
    resolve_corpus_override,
)
from digigraph.graph.state import WorkflowState
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state
from fastapi import HTTPException

pytestmark = pytest.mark.unit


def test_workflow_state_declares_corpus_routing_keys() -> None:
    """LangGraph drops undeclared TypedDict keys — corpus overrides must be listed."""
    keys = WorkflowState.__annotations__
    assert "digisearch_index" in keys
    assert "vault_path_prefix" in keys
    assert "research_system_prompt_override" in keys


def test_initial_graph_state_carries_corpus_overrides() -> None:
    state = _initial_graph_state(
        WorkflowRequest(
            prompt="hi",
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
            research_system_prompt_override="OCC prompt",
        ),
        "wf-corpus",
    )
    assert state["digisearch_index"] == "occ_help"
    assert state["vault_path_prefix"] == "clients/online-compliance-center"
    assert state["research_system_prompt_override"] == "OCC prompt"


def test_initial_graph_state_clears_corpus_overrides_when_none() -> None:
    """Unmapped-tenant clears from server.py must reach checkpointed state.

    Omitting the keys when None left the prior turn's digisearch_index sticky under
    LangGraph last-write-wins — cross-tenant corpus bleed on a reused session_id
    (digichat embeds share subject embed:anonymous across tenants).
    """
    state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-corpus-clear")
    assert "digisearch_index" in state
    assert state["digisearch_index"] is None
    assert "vault_path_prefix" in state
    assert state["vault_path_prefix"] is None
    assert "research_system_prompt_override" in state
    assert state["research_system_prompt_override"] is None
    assert "digi_subject" in state
    assert state["digi_subject"] is None


def test_langgraph_clears_sticky_digisearch_index_on_none() -> None:
    """Two-turn checkpoint merge: occ_help then explicit None must clear the index."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    seen: list[str | None] = []

    def _capture(state: WorkflowState) -> dict:
        seen.append(state.get("digisearch_index"))
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "sticky-corpus-1"}}
    graph.invoke({"prompt": "t1", "digisearch_index": "occ_help"}, config=config)
    graph.invoke({"prompt": "t2", "digisearch_index": None}, config=config)
    assert seen == ["occ_help", None]


def test_langgraph_preserves_corpus_keys_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip digisearch_index."""
    from langgraph.graph import END, START, StateGraph

    seen: dict[str, str | None] = {}

    def _capture(state: WorkflowState) -> dict:
        seen["digisearch_index"] = state.get("digisearch_index")
        seen["vault_path_prefix"] = state.get("vault_path_prefix")
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile()
    graph.invoke(
        {
            "prompt": "x",
            "digisearch_index": "occ_help",
            "vault_path_prefix": "clients/online-compliance-center",
        }
    )
    assert seen["digisearch_index"] == "occ_help"
    assert seen["vault_path_prefix"] == "clients/online-compliance-center"


def test_load_tenant_corpus_map_parses_camel_and_snake() -> None:
    raw = (
        '{"occ":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"},'
        '"digithings":{"digisearch_index":"digithings_docs","vault_path_prefix":"/clients/digithings/"}}'
    )
    table = load_tenant_corpus_map(raw)
    assert table["occ"].digisearch_index == "occ_help"
    assert table["occ"].vault_path_prefix == "clients/online-compliance-center"
    assert table["digithings"].digisearch_index == "digithings_docs"
    assert table["digithings"].vault_path_prefix == "clients/digithings"


def test_load_tenant_corpus_map_lowercases_slug_keys() -> None:
    """Parity with digivault tenant_scope: slug keys are lowercased so OCC matches occ."""
    raw = '{"OCC":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/occ"}}'
    table = load_tenant_corpus_map(raw)
    assert "occ" in table
    assert "OCC" not in table
    assert table["occ"].digisearch_index == "occ_help"


def test_resolve_map_is_authoritative_over_headers() -> None:
    """Multi-tenant: DIGI_TENANT_CORPUS_MAP wins; client corpus headers cannot
    select another tenant's digisearch index / vault prefix (CWE-639). digichat
    still sends matching headers for the tenant — those are redundant once the
    map is set, not a license to override it."""
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        ),
        "digithings": TenantCorpusOverride(
            digisearch_index="digithings_docs",
            vault_path_prefix="clients/digithings",
        ),
    }
    headers = {
        "x-digi-corpus-index": "occ_help",
        "x-digi-vault-prefix": "clients/online-compliance-center",
        "x-digi-tenant": "digithings",
    }
    # Auth tenant digithings + attacker headers naming OCC corpus → map wins.
    out = resolve_corpus_override(
        headers=headers,
        tenant_slug="digithings",
        corpus_map=mapped,
    )
    assert out.digisearch_index == "digithings_docs"
    assert out.vault_path_prefix == "clients/digithings"


def test_resolve_map_ignores_headers_for_unmapped_tenant() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        ),
    }
    out = resolve_corpus_override(
        headers={
            "x-digi-corpus-index": "occ_help",
            "x-digi-vault-prefix": "clients/online-compliance-center",
        },
        tenant_slug="digithings",
        corpus_map=mapped,
    )
    assert out.digisearch_index is None
    assert out.vault_path_prefix is None


def test_resolve_map_ignores_headers_without_tenant_slug() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        ),
    }
    out = resolve_corpus_override(
        headers={"x-digi-corpus-index": "occ_help"},
        tenant_slug=None,
        corpus_map=mapped,
    )
    assert out.digisearch_index is None
    assert out.vault_path_prefix is None


def test_resolve_falls_back_to_map_for_tenant() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
            research_system_prompt="OCC prompt",
        )
    }
    out = resolve_corpus_override(
        headers={},
        tenant_slug="occ",
        corpus_map=mapped,
    )
    assert out.digisearch_index == "occ_help"
    assert out.vault_path_prefix == "clients/online-compliance-center"
    assert out.research_system_prompt == "OCC prompt"


def test_resolve_headers_win_when_map_unset() -> None:
    """Single-tenant (no DIGI_TENANT_CORPUS_MAP): headers may still select corpus."""
    out = resolve_corpus_override(
        headers={
            "x-digi-corpus-index": "other_index",
            "x-digi-vault-prefix": "clients/other",
        },
        corpus_map={},
    )
    assert out.digisearch_index == "other_index"
    assert out.vault_path_prefix == "clients/other"


def test_invalid_map_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set-but-broken map must not silently become {} (CWE-639 fail-open)."""
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", "{not-json")
    with pytest.raises(TenantCorpusMapError, match="not valid JSON"):
        load_tenant_corpus_map()


def test_non_object_map_raises() -> None:
    with pytest.raises(TenantCorpusMapError, match="JSON object"):
        load_tenant_corpus_map("[]")


def test_all_entries_dropped_raises() -> None:
    """Every entry individually unusable → still fail closed, not 'map unset'."""
    with pytest.raises(TenantCorpusMapError, match="no usable"):
        load_tenant_corpus_map('{"!!!":"not-an-object"}')


def test_genuinely_unset_map_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    assert load_tenant_corpus_map() == {}


def test_broken_map_surfaces_503_at_request_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """server._digi_fields_from_request must not fall through to client headers."""
    from types import SimpleNamespace

    from digigraph.models import WorkflowRequest
    from digigraph.server import _with_digi_request_context
    from digikey.models import DigiAuthContext

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", "{not-json")
    auth = DigiAuthContext(subject="user-1", tenant_slug="digithings")
    req = WorkflowRequest(prompt="hi", digisearch_index="occ_help")
    http = SimpleNamespace(
        state=SimpleNamespace(digi_auth=auth, digi_bearer=None),
        headers={"x-digi-corpus-index": "occ_help"},
    )
    with pytest.raises(HTTPException) as exc_info:
        _with_digi_request_context(http, req)
    assert exc_info.value.status_code == 503
    assert "DIGI_TENANT_CORPUS_MAP" in str(exc_info.value.detail)


def test_resolve_map_drops_invalid_index_keeps_vault_prefix() -> None:
    """Invalid digisearch index chars must not reach digisearch, but a valid vault
    prefix from the same map entry must still apply (partial override, not wipe)."""
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="bad index!!",
            vault_path_prefix="clients/online-compliance-center",
        ),
    }
    out = resolve_corpus_override(
        headers={},
        tenant_slug="occ",
        corpus_map=mapped,
    )
    assert out.digisearch_index is None
    assert out.vault_path_prefix == "clients/online-compliance-center"


def test_resolve_headers_drop_invalid_index_when_map_unset() -> None:
    """Single-tenant path: malformed X-Digi-Corpus-Index is ignored; vault prefix
    from headers still applies."""
    out = resolve_corpus_override(
        headers={
            "x-digi-corpus-index": "not a valid index",
            "x-digi-vault-prefix": "clients/other",
        },
        corpus_map={},
    )
    assert out.digisearch_index is None
    assert out.vault_path_prefix == "clients/other"


def test_load_tenant_corpus_map_skips_invalid_slug_and_non_object_entry() -> None:
    """Soft-skip bad rows so one typo does not discard the rest of the map."""
    raw = (
        '{"OCC":{"digisearch_index":"occ_help"},'
        '"ok-tenant":{"digisearch_index":"ok_docs","vault_path_prefix":"clients/ok"},'
        '"also-ok":"not-an-object"}'
    )
    table = load_tenant_corpus_map(raw)
    assert "OCC" not in table  # uppercase fails _SLUG
    assert "also-ok" not in table
    assert table["ok-tenant"].digisearch_index == "ok_docs"
    assert table["ok-tenant"].vault_path_prefix == "clients/ok"
