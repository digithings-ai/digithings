"""Unit tests for digigraph per-tenant corpus routing."""

from __future__ import annotations

import pytest
from digigraph.corpus_routing import (
    TenantCorpusOverride,
    load_tenant_corpus_map,
    resolve_corpus_override,
)
from digigraph.graph.state import WorkflowState
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state

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


def test_resolve_headers_win_over_map() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        )
    }
    headers = {
        "x-digi-corpus-index": "other_index",
        "x-digi-vault-prefix": "clients/other",
        "x-digi-tenant": "occ",
    }
    out = resolve_corpus_override(headers=headers, corpus_map=mapped)
    assert out.digisearch_index == "other_index"
    assert out.vault_path_prefix == "clients/other"


def test_resolve_falls_back_to_map_for_tenant() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
            research_system_prompt="OCC prompt",
        )
    }
    out = resolve_corpus_override(
        headers={"x-digi-tenant": "occ"},
        corpus_map=mapped,
    )
    assert out.digisearch_index == "occ_help"
    assert out.vault_path_prefix == "clients/online-compliance-center"
    assert out.research_system_prompt == "OCC prompt"


def test_invalid_map_json_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", "{not-json")
    assert load_tenant_corpus_map() == {}
