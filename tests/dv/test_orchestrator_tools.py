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
    assert "path_prefix" in params["properties"]
    assert params["required"] == ["vault_path", "path_prefix"]
    # The description must tell the model where a vault_path comes from, or it will
    # invent one instead of reading it off a digisearch hit.
    assert "digisearch" in tool["function"]["description"].lower()


def test_get_note_tool_path_prefix_description_does_not_claim_enforced_isolation() -> None:
    """Same guard as `digivault_search_notes`'s equivalent test: declaring the
    argument (#2239 review) must not overstate it into a tenant-isolation
    guarantee the server does not provide (#2265)."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    prefix_description = tool["function"]["parameters"]["properties"]["path_prefix"][
        "description"
    ].lower()
    assert "isolat" not in prefix_description


def test_get_note_tool_description_warns_against_guessing_the_path() -> None:
    """The description must forbid inventing a vault_path and say where a real one comes
    from. Wording is free (#2306 rephrased "do not guess" to "never invented"); the
    requirement is that both halves of the instruction survive any rewrite."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    description = tool["function"]["description"].lower()
    forbids = any(p in description for p in ("not guess", "never invent", "is never invented"))
    assert forbids, "description must forbid inventing a vault_path"
    assert "prior search hit" in description, "and must say where a real one comes from"


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


def test_search_notes_path_prefix_description_states_the_overwrite_as_unconditional() -> None:
    """Minor 5 (#2265 review, task 9): the #2239-era copy said 'omit it and the
    caller's own corpus prefix is filled in for you', true only when
    digigraph/src/digigraph/orchestration/builtin.py's `_handle_digivault_search`
    merely defaulted a missing argument. That handler now overwrites `path_prefix`
    unconditionally (#2265, closed on the digigraph side by #2240) — whatever the
    model supplies is discarded whether present or absent, not just filled in when
    missing. The description must say the value is not under the model's control at
    all when called through digigraph, and must still flag the D1 deployment's
    functionally-required (D1 has no unscoped mode) nature."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_SEARCH_NOTES
    )
    prefix_description = tool["function"]["parameters"]["properties"]["path_prefix"][
        "description"
    ].lower()
    assert "not actually under your control" in prefix_description
    assert "d1" in prefix_description


def test_get_note_tool_path_prefix_description_states_the_overwrite_as_unconditional() -> None:
    """Important 1 (#2240 final-branch review): this description used to say
    'path_prefix itself is not verified against the caller's actual tenant
    (#2265)' and instruct the model to 'use the same prefix the prior search was
    scoped to' — both false once this branch closed #2265 by making
    digigraph's _handle_digivault_get_note overwrite path_prefix unconditionally,
    and the second was unfollowable regardless, since the prefix a search was
    scoped to is injected server-side and never echoed back to the model. Pin the
    corrected text the same way the digivault_search_notes sibling is pinned."""
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    prefix_description = tool["function"]["parameters"]["properties"]["path_prefix"][
        "description"
    ].lower()
    assert "not actually under your control" in prefix_description
    assert "2265" not in prefix_description
    assert "use the same prefix the prior search was scoped to" not in prefix_description


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
        assert "metadata.vault_path" in text
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
