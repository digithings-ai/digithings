"""Unit tests for the Supabase-backed vault store (digivault.supabase_store).

Deterministic, network-free: a fake client returns canned rows / RPC data. Verifies
the store reconstructs Notes (frontmatter, tags, wikilinks, backlinks) identically to
the filesystem Vault, that the resulting vault is read-only, and that search hits the RPC.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — fake client mirrors the dynamic supabase client

import pytest
from digivault.supabase_store import SupabaseStore, SupabaseStoreError
from digivault.vault import VaultError

pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, data: list[dict[str, Any]], client: "_FakeClient") -> None:
        self._data = data
        self._client = client
        self._like: str | None = None
        self._range: tuple[int, int] | None = None

    def select(self, *_a: Any, **_k: Any) -> "_Query":
        return self

    def like(self, _column: str, pattern: str) -> "_Query":
        self._like = pattern
        return self

    def order(self, *_a: object, **_k: object) -> "_Query":
        return self

    def range(self, start: int, end: int) -> "_Query":
        self._client.range_calls.append((start, end))
        self._range = (start, end)
        return self

    def execute(self) -> _Response:
        rows = self._data
        if self._like is not None:
            pattern = self._like
            prefix = pattern[:-1] if pattern.endswith("%") else pattern
            rows = [r for r in rows if str(r.get("vault_path", "")).startswith(prefix)]
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        return _Response(rows)


class _FakeClient:
    """Minimal stand-in satisfying SupabaseClientProtocol."""

    def __init__(self, rows: list[dict[str, Any]], rpc_data: list[dict[str, Any]] | None = None):
        self._rows = rows
        self._rpc_data = rpc_data or []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.range_calls: list[tuple[int, int]] = []

    def table(self, _name: str) -> _Query:
        return _Query(self._rows, self)

    def rpc(self, fn: str, params: dict[str, Any]) -> _Query:
        self.rpc_calls.append((fn, params))
        return _Query(self._rpc_data, self)


_ROWS = [
    {
        "vault_path": "digigraph",
        "title": "digigraph",
        "frontmatter": {
            "title": "digigraph",
            "type": "module",
            "status": "reviewed",
            "tags": ["core", "orchestration"],
        },
        "body_markdown": "# digigraph\n> hub\n\nOrchestrates [[digisearch|digisearch]].",
    },
    {
        "vault_path": "digisearch",
        "title": "digisearch",
        "frontmatter": {
            "title": "digisearch",
            "type": "module",
            "status": "reviewed",
            "tags": ["core", "retrieval"],
        },
        "body_markdown": "# digisearch\n> rag pipeline",
    },
]


def test_reconstructs_notes_with_tags_and_backlinks() -> None:
    vault = SupabaseStore(_FakeClient(_ROWS)).load_vault()

    assert {n.name for n in vault.list_notes()} == {"digigraph", "digisearch"}
    digigraph = vault.get_note("digigraph")
    assert digigraph is not None
    assert digigraph.title == "digigraph"
    assert set(digigraph.tags) == {"core", "orchestration"}
    # The [[digisearch]] wikilink resolves into a backlink — same indexing as on disk.
    assert vault.backlinks("digisearch") == ("digigraph",)


def test_read_text_uses_body_cache() -> None:
    vault = SupabaseStore(_FakeClient(_ROWS)).load_vault()
    body = vault.read_text("digigraph")
    assert "Orchestrates" in body and "digigraph" in body


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


def test_search_calls_rpc_and_returns_models() -> None:
    hit = {
        "vault_path": "digikey",
        "title": "digikey",
        "note_type": "module",
        "summary": "auth control plane",
        "body_markdown": "JWT auth with scoped API keys.",
        "tags": ["support", "auth"],
        "wikilinks": [],
        "rank": 0.9,
    }
    client = _FakeClient([], rpc_data=[hit])
    results = SupabaseStore(client).search("authentication jwt", limit=3)

    assert results[0].vault_path == "digikey"  # a VaultSearchHit model, not a raw dict
    assert results[0].tags == ("support", "auth")  # list coerced to tuple
    assert client.rpc_calls == [
        (
            "search_architecture_notes",
            {"query": "authentication jwt", "match_limit": 3, "path_prefix": None},
        )
    ]


def test_search_passes_path_prefix_to_rpc() -> None:
    hit_in = {
        "vault_path": "clients/occ/faq",
        "title": "faq",
        "note_type": "note",
        "summary": "occ faq",
        "body_markdown": "password reset",
        "tags": [],
        "wikilinks": [],
        "rank": 0.5,
    }
    hit_out = {
        **hit_in,
        "vault_path": "clients/other/faq",
        "title": "other",
    }
    client = _FakeClient([], rpc_data=[hit_in, hit_out])
    results = SupabaseStore(client).search("password", limit=5, path_prefix="clients/occ")

    assert [h.vault_path for h in results] == ["clients/occ/faq"]
    assert client.rpc_calls == [
        (
            "search_architecture_notes",
            {"query": "password", "match_limit": 5, "path_prefix": "clients/occ"},
        )
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


def test_list_notes_filters_by_prefix_and_paginates() -> None:
    rows = [
        {
            "vault_path": f"clients/digithings/n{i}",
            "title": f"n{i}",
            "frontmatter": {},
            "body_markdown": "body",
        }
        for i in range(7)
    ] + [
        {"vault_path": "clients/other/x", "title": "x", "frontmatter": {}, "body_markdown": "body"}
    ]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_notes(path_prefix="clients/digithings", page_size=3)
    assert len(out) == 7
    assert all(r["vault_path"].startswith("clients/digithings/") for r in out)
    assert len(client.range_calls) >= 3


def test_list_notes_without_prefix_returns_all() -> None:
    rows = [{"vault_path": "a/b", "title": "t", "frontmatter": {}, "body_markdown": "x"}]
    store = SupabaseStore(_FakeClient(rows))
    assert len(store.list_notes()) == 1


def test_list_notes_stops_on_short_page() -> None:
    rows = [
        {"vault_path": f"p/n{i}", "title": "t", "frontmatter": {}, "body_markdown": "x"}
        for i in range(2)
    ]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_notes(path_prefix="p", page_size=500)
    assert len(out) == 2
    assert len(client.range_calls) == 1
