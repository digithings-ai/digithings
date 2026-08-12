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
