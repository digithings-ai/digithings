"""Unit tests for the Supabase-backed vault store (digivault.supabase_store).

Deterministic, network-free: a fake client returns canned rows / RPC data. Verifies
the store reconstructs Notes (frontmatter, tags, wikilinks, backlinks) identically to
the filesystem Vault, that the resulting vault is read-only, and that search hits the RPC.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — fake client mirrors the dynamic supabase client

import pytest
from digivault.models import NoteRow
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
    assert all(isinstance(r, NoteRow) for r in out)
    assert all(r.vault_path.startswith("clients/digithings/") for r in out)
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


@pytest.mark.parametrize("page_size", [0, -1])
def test_list_notes_rejects_non_positive_page_size(page_size: int) -> None:
    """page_size <= 0 must fail before any I/O, not loop forever (finding: unbounded loop)."""
    client = _FakeClient([])
    store = SupabaseStore(client)
    with pytest.raises(ValueError, match=str(page_size)):
        store.list_notes(path_prefix="clients/digithings", page_size=page_size)
    assert client.range_calls == []


def test_list_notes_prefix_excludes_hyphen_suffix_collision() -> None:
    """`clients/digithings` must not also match `clients/digithings-archive` (multi-tenant
    isolation). The server-side `.like()` pattern `clients/digithings%` matches both, so this
    only passes if the client-side re-check (vault_path == prefix or startswith prefix + "/")
    is still in place."""
    rows = [
        {
            "vault_path": "clients/digithings/note1",
            "title": "note1",
            "frontmatter": {},
            "body_markdown": "body",
        },
        {
            "vault_path": "clients/digithings-archive/note2",
            "title": "note2",
            "frontmatter": {},
            "body_markdown": "body",
        },
    ]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_notes(path_prefix="clients/digithings")
    assert [r.vault_path for r in out] == ["clients/digithings/note1"]


def test_list_notes_returns_note_row_models() -> None:
    """`list_notes` must return validated `NoteRow` models, not raw dicts (CodeRabbit
    finding: field names/types were checked nowhere and consumers used `.get(...)`)."""
    rows = [{"vault_path": "a/b", "title": "t", "frontmatter": {"k": "v"}, "body_markdown": "x"}]
    store = SupabaseStore(_FakeClient(rows))
    out = store.list_notes()
    assert len(out) == 1
    assert isinstance(out[0], NoteRow)
    assert out[0] == NoteRow(vault_path="a/b", title="t", frontmatter={"k": "v"}, body_markdown="x")


def test_list_raw_returns_columns_outside_note_row_as_plain_dicts() -> None:
    """#2239 review Important I2: `list_notes` validates through `NoteRow`, which
    only carries four columns and ignores everything else -- a caller needing
    `architecture_notes`'s top-level `note_type`/`summary`/`wikilinks` columns
    (`scripts/d1_sync.py`'s D1 backfill) cannot get them back out of a `NoteRow`.
    `list_raw` skips that validation step and hands back exactly the columns its
    `select` asked for."""
    rows = [
        {
            "vault_path": "clients/x/a",
            "title": "A",
            "frontmatter": {},
            "body_markdown": "body",
            "note_type": "reference",
            "summary": "a summary",
            "wikilinks": ["b"],
        }
    ]
    store = SupabaseStore(_FakeClient(rows))
    out = store.list_raw(
        select="vault_path,title,frontmatter,body_markdown,note_type,summary,wikilinks"
    )
    assert out == rows


def test_list_raw_filters_by_prefix_and_paginates() -> None:
    rows = [
        {"vault_path": f"clients/digithings/n{i}", "note_type": "reference"} for i in range(7)
    ] + [{"vault_path": "clients/other/x", "note_type": "reference"}]
    client = _FakeClient(rows)
    store = SupabaseStore(client)
    out = store.list_raw(
        select="vault_path,note_type", path_prefix="clients/digithings", page_size=3
    )
    assert len(out) == 7
    assert all(r["vault_path"].startswith("clients/digithings/") for r in out)
    assert len(client.range_calls) >= 3


def test_list_raw_prefix_excludes_hyphen_suffix_collision() -> None:
    """Same client-side re-check as `list_notes` -- `clients/digithings` must not
    also match `clients/digithings-archive`."""
    rows = [
        {"vault_path": "clients/digithings/note1", "note_type": "reference"},
        {"vault_path": "clients/digithings-archive/note2", "note_type": "reference"},
    ]
    store = SupabaseStore(_FakeClient(rows))
    out = store.list_raw(select="vault_path,note_type", path_prefix="clients/digithings")
    assert [r["vault_path"] for r in out] == ["clients/digithings/note1"]


def test_list_raw_rejects_non_positive_page_size() -> None:
    client = _FakeClient([])
    store = SupabaseStore(client)
    with pytest.raises(ValueError, match="0"):
        store.list_raw(select="vault_path", page_size=0)
    assert client.range_calls == []


def test_list_notes_tolerates_extra_columns_and_null_frontmatter() -> None:
    """A realistic full table row carries far more columns than the four this model
    needs (slug, note_type, status, tags, summary, wikilinks, sources, timestamps),
    and `frontmatter` (jsonb) / `body_markdown` can legitimately be SQL NULL. Neither
    should raise -- extras are ignored, nulls normalize to this model's defaults."""
    rows = [
        {
            "vault_path": "clients/acme/note1",
            "title": "Note One",
            "frontmatter": None,
            "body_markdown": None,
            "slug": "note1",
            "note_type": "note",
            "status": "published",
            "tags": ["a", "b"],
            "summary": "a summary",
            "wikilinks": [],
            "sources": [],
            "updated_at": "2026-08-01T00:00:00Z",
            "created_at": "2026-08-01T00:00:00Z",
        }
    ]
    store = SupabaseStore(_FakeClient(rows))
    out = store.list_notes()
    assert len(out) == 1
    note = out[0]
    assert isinstance(note, NoteRow)
    assert note.vault_path == "clients/acme/note1"
    assert note.title == "Note One"
    assert note.frontmatter == {}
    assert note.body_markdown == ""
