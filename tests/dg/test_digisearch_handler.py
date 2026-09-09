"""Unit tests for the digisearch orchestrator tool's tenant (index_name) scoping.

`_handle_digisearch` (digigraph.orchestration.builtin) is the digisearch half of the
same tenant boundary #2265 closed on the digivault side (path_prefix). See
tests/dg/test_digivault_tool.py for the vault-handler equivalents this mirrors.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from digigraph.orchestration.registry import ToolContext

pytestmark = pytest.mark.unit


def _ctx(**overrides: object) -> ToolContext:
    defaults: dict[str, object] = {
        "session_id": "sess-1",
        "run_data_dir": None,
        "index_name": "digithings_docs",
        "index_config": {},
        "state": {},
        "request_id": "rid-1",
    }
    defaults.update(overrides)
    return ToolContext(**defaults)  # type: ignore[arg-type]


def test_handle_digisearch_overwrites_model_supplied_index_name() -> None:
    """Important 4 (#2240 final-branch review): a model-supplied index_name must
    never reach digisearch unchecked. Before this fix, `_handle_digisearch` only
    *defaulted* index_name when the model omitted it — the same conditional
    pattern the vault handlers were already fixed away from for path_prefix.
    Verified against the real tool loop: a model-supplied index_name of
    'occ_help' reached digisearch and overrode the session's own
    'digithings_docs' index, reading the other tenant's vector corpus. Mirrors
    _handle_digivault_search's / _handle_digivault_get_note's unconditional
    path_prefix overwrite."""
    from digigraph.orchestration.builtin import _handle_digisearch

    ctx = _ctx(index_name="digithings_docs")
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch({"query": "q", "index_name": "occ_help"}, ctx)

    call_args = mock_invoke.call_args
    assert call_args.args[2]["index_name"] == "digithings_docs"
    assert call_args.kwargs["default_index_name"] == "digithings_docs"


def test_handle_digisearch_uses_context_index_name_when_model_omits_it() -> None:
    """Baseline: with no model-supplied index_name, the session's own index_name
    still reaches digisearch (unconditional overwrite must not regress this)."""
    from digigraph.orchestration.builtin import _handle_digisearch

    ctx = _ctx(index_name="digithings_docs")
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch({"query": "q"}, ctx)

    call_args = mock_invoke.call_args
    assert call_args.args[2]["index_name"] == "digithings_docs"


def test_handle_digisearch_no_hits_still_dict_for_trace() -> None:
    """Sanity: the overwrite must not disturb the existing zero-hit trace shape
    (explicitly out of scope to change per the task brief)."""
    from digigraph.orchestration.builtin import _handle_digisearch

    ctx = _ctx(index_name="digithings_docs")
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ):
        out = _handle_digisearch({"query": "q", "index_name": "occ_help"}, ctx)

    assert out == {"content": "No results found.", "results": [], "rag_sources": []}


def test_handle_digisearch_fetch_all_overwrites_model_supplied_index_name() -> None:
    """#2265 sibling of `_handle_digisearch`: fetch_all must not let a model-supplied
    index_name reach digisearch. Latent today (not in digichat allowlist) but the
    production comment warns that leaving this on default-if-missing reopens the
    tenant boundary the moment the tool is allowlisted."""
    from digigraph.orchestration.builtin import _handle_digisearch_fetch_all

    ctx = _ctx(index_name="digithings_docs")
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch_fetch_all({"query": "q", "index_name": "occ_help"}, ctx)

    call_args = mock_invoke.call_args
    assert call_args.args[1] == "digisearch_fetch_all"
    assert call_args.args[2]["index_name"] == "digithings_docs"
    assert call_args.kwargs["default_index_name"] == "digithings_docs"


def test_handle_digisearch_research_delegate_overwrites_model_supplied_index_name() -> None:
    """#2265 third shape: research_delegate must overwrite index_name unconditionally
    even though it is hub-gated / not allowlisted in production today."""
    from digigraph.orchestration.builtin import _handle_digisearch_research_delegate

    ctx = _ctx(index_name="digithings_docs")
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={
            "ok": True,
            "data": {"formatted_context": "ctx", "results": [], "rag_sources": []},
        },
    ) as mock_invoke:
        _handle_digisearch_research_delegate(
            {"user_message": "summarize", "index_name": "occ_help"},
            ctx,
        )

    call_args = mock_invoke.call_args
    assert call_args.args[1] == "digisearch_research_delegate"
    assert call_args.args[2]["index_name"] == "digithings_docs"
    assert call_args.kwargs["default_index_name"] == "digithings_docs"


# ---------------------------------------------------------------------------
# _merged_digisearch_filters — every digisearch path (search / fetch_all /
# research_delegate) funnels workflow + per-call filters through this helper.
# Wrong merge silently drops workflow research_filters or evidence_tier
# preference, so retrieval constraints never reach digisearch.
# ---------------------------------------------------------------------------


def test_merged_digisearch_filters_returns_none_when_empty() -> None:
    from digigraph.orchestration.builtin import _merged_digisearch_filters

    assert _merged_digisearch_filters(_ctx(state={}), {}) is None
    assert _merged_digisearch_filters(_ctx(state={"research_filters": []}), {}) is None
    assert _merged_digisearch_filters(_ctx(state={"evidence_tier_preference": []}), {}) is None


def test_merged_digisearch_filters_combines_workflow_args_and_evidence_tier() -> None:
    """Order is workflow filters, then tool-arg filters, then evidence_tier `in`."""
    from digigraph.orchestration.builtin import _merged_digisearch_filters

    wf = {"field": "region", "op": "eq", "value": "EU"}
    arg = {"field": "year", "op": "eq", "value": 2024}
    ctx = _ctx(
        state={
            "research_filters": [wf, "skip-me", None],
            "evidence_tier_preference": ["peer_reviewed", "working_paper"],
        }
    )
    merged = _merged_digisearch_filters(ctx, {"filters": [arg, 42]})
    assert merged == [
        wf,
        arg,
        {
            "field": "evidence_tier",
            "op": "in",
            "value": ["peer_reviewed", "working_paper"],
        },
    ]


def test_merged_digisearch_filters_ignores_non_list_state_and_args() -> None:
    """Garbage shapes must not raise or inject a broken filter list."""
    from digigraph.orchestration.builtin import _merged_digisearch_filters

    ctx = _ctx(state={"research_filters": {"field": "x"}, "evidence_tier_preference": "peer"})
    assert _merged_digisearch_filters(ctx, {"filters": {"field": "y"}}) is None


def test_handle_digisearch_forwards_merged_filters_to_invoke() -> None:
    """Handler must put the merged list on args_eff['filters'] before invoke.

    A regression that builds the merge but never assigns it would leave
    workflow research_filters / evidence_tier preference on the floor while
    unit tests of the helper alone still pass.
    """
    from digigraph.orchestration.builtin import _handle_digisearch

    wf = {"field": "sourceType", "op": "eq", "value": "doc"}
    arg = {"field": "itemType", "op": "eq", "value": "page"}
    ctx = _ctx(
        state={
            "research_filters": [wf],
            "evidence_tier_preference": ["peer_reviewed"],
        }
    )
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch({"query": "q", "filters": [arg]}, ctx)

    forwarded = mock_invoke.call_args.args[2]["filters"]
    assert forwarded == [
        wf,
        arg,
        {"field": "evidence_tier", "op": "in", "value": ["peer_reviewed"]},
    ]


def test_handle_digisearch_omits_filters_key_when_merge_empty() -> None:
    """No filters in state/args → do not invent an empty filters key for digisearch."""
    from digigraph.orchestration.builtin import _handle_digisearch

    ctx = _ctx(state={})
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch({"query": "q"}, ctx)

    assert "filters" not in mock_invoke.call_args.args[2]


def test_handle_digisearch_fetch_all_clamps_max_results_to_project_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator-side clamp: a model-supplied max_results above the project
    limit must not reach digisearch (resource bound / DoS surface)."""
    from digigraph.orchestration.builtin import _handle_digisearch_fetch_all

    monkeypatch.setenv("DIGI_MAX_ROWS_PER_FETCH", "100")
    ctx = _ctx()
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch_fetch_all({"query": "q", "max_results": 50_000}, ctx)

    assert mock_invoke.call_args.args[2]["max_results"] == 100


def test_handle_digisearch_fetch_all_defaults_max_results_to_project_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the model omits max_results, the project cap is still applied."""
    from digigraph.orchestration.builtin import _handle_digisearch_fetch_all

    monkeypatch.setenv("DIGI_MAX_ROWS_PER_FETCH", "75")
    ctx = _ctx()
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch_fetch_all({"query": "q"}, ctx)

    assert mock_invoke.call_args.args[2]["max_results"] == 75


def test_handle_digisearch_fetch_all_keeps_max_results_at_or_below_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Values already within the cap must not be raised or rewritten."""
    from digigraph.orchestration.builtin import _handle_digisearch_fetch_all

    monkeypatch.setenv("DIGI_MAX_ROWS_PER_FETCH", "100")
    ctx = _ctx()
    with patch(
        "digigraph.orchestration.builtin.invoke_digisearch_tool",
        return_value={"ok": True, "data": {"results": [], "total": 0}},
    ) as mock_invoke:
        _handle_digisearch_fetch_all({"query": "q", "max_results": 40}, ctx)

    assert mock_invoke.call_args.args[2]["max_results"] == 40


@pytest.mark.unit
def test_search_payload_keeps_metadata_addressable_as_json() -> None:
    """#2306: metadata must reach the model as an object, not a Python repr.

    digivault_get_note's description tells the model to read a digisearch hit's
    metadata.vault_path. str(dict) renders single-quoted Python repr, which is not
    addressable as JSON — and the 300-char clip is then applied to that repr. Realistic
    digisearch metadata measures 302 chars with vault_path serialized last, so the exact
    key the model was told to read was the first thing truncated, producing a half-path
    that 404s against digivault.
    """
    from digigraph.orchestration.builtin import _search_payload_for_llm

    vault_path = "clients/digithings/digithings-security-md__security-threat-model-stride-table"
    metadata = {
        "title": "Security",
        "section": "Threat model > STRIDE table",
        "source": "SECURITY.md",
        "tags": ["security", "threat-model"],
        "ingested_at": "2026-08-01T00:00:00Z",
        "chunk_index": 3,
        "doc_type": "markdown",
        "vault_path": vault_path,
    }
    payload = _search_payload_for_llm([{"content": "x", "metadata": metadata}], 1)

    row = payload["preview"][0]
    assert isinstance(row["metadata"], dict), "metadata must stay an object, not str(dict)"
    assert row["metadata"]["vault_path"] == vault_path, "the full path must survive intact"
    # And it must survive a JSON round trip, since this payload is json.dumps'd for the LLM.
    assert json.loads(json.dumps(payload))["preview"][0]["metadata"]["vault_path"] == vault_path


@pytest.mark.unit
def test_search_payload_clips_oversized_metadata_as_json_not_python_repr() -> None:
    """An oversized structured value still has to be bounded for context, but bounding it
    must not cost the addressability of its other keys."""
    from digigraph.orchestration.builtin import _LLM_SEARCH_PREVIEW_CHARS, _search_payload_for_llm

    huge = {"note": "y" * (_LLM_SEARCH_PREVIEW_CHARS * 2), "vault_path": "clients/x/y"}
    payload = _search_payload_for_llm([{"content": "x", "metadata": huge}], 1)

    row = payload["preview"][0]
    # The object survives; only the oversized VALUE is clipped, so a short critical key
    # sitting next to a huge one is still addressable.
    assert isinstance(row["metadata"], dict)
    assert row["metadata"]["vault_path"] == "clients/x/y"
    assert row["metadata"]["note"].endswith("...")
    assert len(row["metadata"]["note"]) < len(huge["note"])


@pytest.mark.unit
def test_digisearch_rows_are_marked_truncated_too() -> None:
    """Regression: the truncation flag must be emitted by BOTH search sinks.

    Marking only digivault rows is worse than marking none. The prompt tells the model a
    row without `truncated` is complete, so an unmarked digisearch row reads as "I have
    seen all of this" — the exact #2306 inference, reintroduced on the sink that returns
    most hits. digisearch rows also arrive with their own upstream `content_truncated`
    (its 500-char preview cap) before digigraph clips again to 300, so either signal must
    mark the row.
    """
    from digigraph.orchestration.builtin import (
        _LLM_SEARCH_PREVIEW_CHARS,
        _mark_truncated_excerpts,
        _search_payload_for_llm,
    )

    results = [
        # Clipped by digigraph's own 300-char budget.
        {"content": "a" * (_LLM_SEARCH_PREVIEW_CHARS + 50), "doc_id": "SECURITY.md"},
        # Short here, but digisearch already told us it clipped upstream.
        {"content": "short", "doc_id": "README.md", "content_truncated": True},
        # Genuinely complete: must stay unmarked.
        {"content": "complete", "doc_id": "TINY.md", "content_truncated": False},
    ]
    payload = _search_payload_for_llm(results, len(results))
    _mark_truncated_excerpts(payload, results, load_hint="that row's metadata.vault_path")

    rows = payload["preview"]
    assert rows[0]["truncated"] is True, "digigraph's own clip must mark the row"
    assert rows[1]["truncated"] is True, "upstream content_truncated must mark the row"
    assert "truncated" not in rows[2], "a complete row must not be flagged"
    assert payload["excerpts_truncated"] is True
    assert "metadata.vault_path" in payload["next_step"], "hint must name THIS sink's key"
    assert "doc_id" not in payload["next_step"], "digisearch doc_id is a repo path, not loadable"
