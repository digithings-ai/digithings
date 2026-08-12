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
