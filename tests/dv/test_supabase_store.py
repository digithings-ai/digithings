"""Unit tests for the Supabase-backed vault store (digivault.supabase_store).

Deterministic, network-free: a fake client returns canned rows / RPC data. Verifies
the store reconstructs Notes (frontmatter, tags, wikilinks, backlinks) identically to
the filesystem Vault, that the resulting vault is read-only, and that search hits the RPC.
"""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — fake client mirrors the dynamic supabase client

import pytest

from digivault.supabase_store import SupabaseStore, SupabaseStoreError
from digivault.vault import VaultError

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def execute(self) -> _Response:
        return _Response(self._data)


class _FakeClient:
    """Minimal stand-in satisfying SupabaseClientProtocol."""

    def __init__(self, rows: list[dict[str, Any]], rpc_data: list[dict[str, Any]] | None = None):
        self._rows = rows
        self._rpc_data = rpc_data or []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, _name: str) -> _Query:
        return _Query(self._rows)

    def rpc(self, fn: str, params: dict[str, Any]) -> _Query:
        self.rpc_calls.append((fn, params))
        return _Query(self._rpc_data)


_ROWS = [
    {
        "vault_path": "digigraph",
        "title": "DigiGraph",
        "frontmatter": {
            "title": "DigiGraph",
            "type": "module",
            "status": "reviewed",
            "tags": ["core", "orchestration"],
        },
        "body_markdown": "# DigiGraph\n> hub\n\nOrchestrates [[digisearch|DigiSearch]].",
    },
    {
        "vault_path": "digisearch",
        "title": "DigiSearch",
        "frontmatter": {
            "title": "DigiSearch",
            "type": "module",
            "status": "reviewed",
            "tags": ["core", "retrieval"],
        },
        "body_markdown": "# DigiSearch\n> rag pipeline",
    },
]


def test_reconstructs_notes_with_tags_and_backlinks() -> None:
    vault = SupabaseStore(_FakeClient(_ROWS)).load_vault()

    assert {n.name for n in vault.list_notes()} == {"digigraph", "digisearch"}
    digigraph = vault.get_note("digigraph")
    assert digigraph is not None
    assert digigraph.title == "DigiGraph"
    assert set(digigraph.tags) == {"core", "orchestration"}
    # The [[digisearch]] wikilink resolves into a backlink — same indexing as on disk.
    assert vault.backlinks("digisearch") == ("digigraph",)


def test_read_text_uses_body_cache() -> None:
    vault = SupabaseStore(_FakeClient(_ROWS)).load_vault()
    body = vault.read_text("digigraph")
    assert "Orchestrates" in body and "DigiGraph" in body


def test_store_backed_vault_is_read_only() -> None:
    vault = SupabaseStore(_FakeClient(_ROWS)).load_vault()
    with pytest.raises(VaultError, match="read-only"):
        vault.create_note("whatever")
    with pytest.raises(VaultError, match="read-only"):
        vault.set_frontmatter("digigraph", {"status": "stub"})


def test_lint_runs_on_store_backed_vault() -> None:
    report = SupabaseStore(_FakeClient(_ROWS)).load_vault().lint()
    assert report.ok is True
    assert report.note_count == 2


def test_blank_vault_path_rows_are_skipped() -> None:
    rows = [*_ROWS, {"vault_path": "  ", "title": "junk", "frontmatter": {}, "body_markdown": ""}]
    vault = SupabaseStore(_FakeClient(rows)).load_vault()
    assert len(vault.list_notes()) == 2


def test_search_calls_rpc_with_query_and_limit() -> None:
    client = _FakeClient([], rpc_data=[{"vault_path": "digikey", "title": "DigiKey", "rank": 0.9}])
    results = SupabaseStore(client).search("authentication jwt", limit=3)

    assert results[0]["vault_path"] == "digikey"
    assert client.rpc_calls == [
        ("search_architecture_notes", {"query": "authentication jwt", "match_limit": 3})
    ]


def test_from_env_raises_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "CORE_SUPABASE_URL",
        "SUPABASE_URL",
        "CORE_SUPABASE_ANON_KEY",
        "CORE_SUPABASE_SERVICE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SupabaseStoreError, match="not configured"):
        SupabaseStore.from_env()
