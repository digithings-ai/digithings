"""Unit tests for the digivault orchestrator tool manifest.

No FastAPI/digikey dependency here — `orchestrator_tools.py` is pure Python (a
manifest of OpenAI-style tool dicts), so unlike `test_server.py` this file needs
no `pytest.importorskip` guards.
"""

from __future__ import annotations

import pytest
from digivault.orchestrator_tools import (
    ORCHESTRATOR_TOOL_NAMES,
    TOOL_VAULT_GET_NOTE,
    TOOL_VAULT_SEARCH_NOTES,
    build_orchestrator_tool_manifest,
)

pytestmark = pytest.mark.unit


def test_get_note_tool_is_in_the_manifest_with_a_vault_path_argument() -> None:
    assert TOOL_VAULT_GET_NOTE in ORCHESTRATOR_TOOL_NAMES
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    params = tool["function"]["parameters"]
    assert "vault_path" in params["properties"]
    assert params["required"] == ["vault_path"]
    # The description must tell the model where a vault_path comes from, or it will
    # invent one instead of reading it off a digisearch hit.
    assert "digisearch" in tool["function"]["description"].lower()


def test_get_note_tool_description_warns_against_guessing_the_path() -> None:
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    description = tool["function"]["description"].lower()
    assert "do not guess" in description or "not guess" in description


def test_search_notes_description_does_not_claim_supabase_is_the_primary_backend() -> None:
    """Since Task 2, D1 wins ahead of both the filesystem vault and Supabase.

    The old copy claimed Supabase FTS was the fallback used "otherwise" (i.e. whenever
    DIGIVAULT_ROOT was unset) with no mention of D1 at all — no longer true.
    """
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_SEARCH_NOTES
    )
    description = tool["function"]["description"].lower()
    assert "d1" in description
    d1_pos = description.index("d1")
    supabase_pos = description.index("supabase")
    assert d1_pos < supabase_pos


def test_search_notes_path_prefix_description_does_not_claim_enforced_isolation() -> None:
    """`path_prefix` is filled in by the caller only when the model omits it

    (digigraph/src/digigraph/orchestration/builtin.py:227) — a model that supplies its
    own value gets exactly that corpus, unchecked. The description must not claim this
    argument isolates multi-tenant corpora; it merely scopes the search (#2265).
    """
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_SEARCH_NOTES
    )
    prefix_description = tool["function"]["parameters"]["properties"]["path_prefix"][
        "description"
    ].lower()
    assert "isolat" not in prefix_description


def test_search_notes_path_prefix_description_states_the_fill_in_as_conditional() -> None:
    """#2239 review, Minor M4: the old copy said 'omit it and the caller's own corpus
    prefix is filled in for you' unconditionally, but
    digigraph/src/digigraph/orchestration/builtin.py:227 only does that when
    `context.vault_path_prefix` is truthy (it defaults to `None`). With no corpus
    context, omitting the argument fills in nothing and, on a D1 deployment, the
    search then fails. The description must say so, not promise an unconditional
    fill-in — and must not call the argument merely 'Optional' with no caveat, since a
    D1 deployment hard-refuses without a resolved prefix."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_SEARCH_NOTES
    )
    prefix_description = tool["function"]["parameters"]["properties"]["path_prefix"][
        "description"
    ].lower()
    assert "corpus context" in prefix_description
    assert "d1" in prefix_description


def test_get_note_tool_description_names_both_search_shapes() -> None:
    """#2239 review, Minor M3: the old copy said to take vault_path 'from that hit's
    metadata', true only for digisearch (which stamps metadata['vault_path'] for
    vault-sourced content via scripts/vectorize_sync.py). digivault_search_notes hits,
    once reshaped by digigraph's _handle_digivault_search, carry the path at `doc_id`
    instead, with `metadata` holding only title/tags — a model that only ever used
    digivault_search_notes would find nothing at metadata.vault_path and invent a
    path. Both shapes must be named, in both the tool description and the vault_path
    parameter description (a caller may only show the model one of the two)."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    description = tool["function"]["description"].lower()
    param_description = tool["function"]["parameters"]["properties"]["vault_path"][
        "description"
    ].lower()
    for text in (description, param_description):
        assert "metadata.vault_path" in text or "metadata" in text
        assert "doc_id" in text


def test_get_note_tool_description_states_the_d1_only_backend_caveat() -> None:
    """#2239 review, Minor M7: `digivault_get_note` is D1-only by design (no
    filesystem/Supabase fallback), so on a non-D1 deployment every call 503s and the
    model would see only a bare 'Server error 503 Service Unavailable' unless warned —
    the same caveat `digivault_search_notes`'s reworked description already states for
    its own backend precedence."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    description = tool["function"]["description"].lower()
    assert "d1-only" in description or "d1 only" in description
    assert "fallback" in description
