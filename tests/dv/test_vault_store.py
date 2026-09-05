"""VaultStore parity tests — FilesystemStore vs PostgresStore (#1142)."""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from digivault.postgres_store import PostgresStore, PostgresStoreError
from digivault.vault import VaultError

from digivault import FilesystemStore, VaultStore

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, table: "_FakeTable") -> None:
        self._table = table
        self._filters: dict[str, Any] = {}
        self._payload: Any = None
        self._op = "select"
        self._order: str | None = None
        self._range: tuple[int, int] | None = None

    def select(self, cols: str) -> _FakeQuery:
        self._op = "select"
        return self

    def eq(self, key: str, value: Any) -> _FakeQuery:
        self._filters[key] = value
        return self

    def order(self, key: str) -> _FakeQuery:
        self._order = key
        return self

    def range(self, start: int, end: int) -> _FakeQuery:
        self._table.range_calls.append((start, end))
        self._range = (start, end)
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> _FakeQuery:
        del on_conflict
        self._op = "upsert"
        self._payload = row
        return self

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        self._op = "insert"
        self._payload = row
        return self

    def update(self, row: dict[str, Any]) -> _FakeQuery:
        self._op = "update"
        self._payload = row
        return self

    def delete(self) -> _FakeQuery:
        self._op = "delete"
        return self

    def execute(self) -> _Resp:
        if self._op == "select":
            rows = [
                r for r in self._table.rows if all(r.get(k) == v for k, v in self._filters.items())
            ]
            if self._order:
                rows = sorted(rows, key=lambda r: str(r.get(self._order) or ""))
            if self._range is not None:
                start, end = self._range
                rows = rows[start : end + 1]
            elif self._table.max_rows is not None:
                # Unpaginated select: PostgREST silently truncates at max-rows.
                rows = rows[: self._table.max_rows]
            return _Resp(rows)
        if self._op == "upsert":
            row = dict(self._payload)
            key = (row.get("vault"), row.get("vault_path"))
            for i, existing in enumerate(self._table.rows):
                if (existing.get("vault"), existing.get("vault_path")) == key:
                    self._table.rows[i] = {**existing, **row}
                    return _Resp([self._table.rows[i]])
            self._table.rows.append(row)
            return _Resp([row])
        if self._op == "insert":
            row = dict(self._payload)
            path_key = (row.get("vault"), row.get("vault_path"))
            slug_key = (row.get("vault"), row.get("slug"))
            for existing in self._table.rows:
                if (existing.get("vault"), existing.get("vault_path")) == path_key:
                    raise VaultError(f"duplicate vault_path: {path_key!r}")
                if (existing.get("vault"), existing.get("slug")) == slug_key:
                    raise VaultError(f"duplicate slug: {slug_key!r}")
            self._table.rows.append(row)
            return _Resp([row])
        if self._op == "update":
            updated: list[dict[str, Any]] = []
            for i, existing in enumerate(self._table.rows):
                if all(existing.get(k) == v for k, v in self._filters.items()):
                    self._table.rows[i] = {**existing, **dict(self._payload)}
                    updated.append(self._table.rows[i])
            return _Resp(updated)
        if self._op == "delete":
            kept = [
                r
                for r in self._table.rows
                if not all(r.get(k) == v for k, v in self._filters.items())
            ]
            deleted = [r for r in self._table.rows if r not in kept]
            self._table.rows[:] = kept
            return _Resp(deleted)
        raise AssertionError(f"unknown op {self._op}")


class _FakeTable:
    def __init__(self, rows: list[dict[str, Any]], *, max_rows: int | None = None) -> None:
        self.rows = rows
        self.max_rows = max_rows
        self.range_calls: list[tuple[int, int]] = []

    def select(self, cols: str) -> _FakeQuery:
        return _FakeQuery(self).select(cols)

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> _FakeQuery:
        return _FakeQuery(self).upsert(row, on_conflict=on_conflict)

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self).insert(row)

    def update(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self).update(row)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self).delete()

    def eq(self, key: str, value: Any) -> _FakeQuery:
        return _FakeQuery(self).eq(key, value)


class _FakeClient:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, *, max_rows: int | None = None
    ) -> None:
        self._table = _FakeTable(list(rows or []), max_rows=max_rows)

    @property
    def range_calls(self) -> list[tuple[int, int]]:
        return self._table.range_calls

    def table(self, name: str) -> _FakeTable:
        del name
        return self._table


def _note_row(
    slug: str,
    *,
    vault: str = "finance",
    body: str = "",
    tags: list[str] | None = None,
    wikilinks: list[str] | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    tags = list(tags or [])
    wikilinks = list(wikilinks or [])
    title = title or slug
    return {
        "vault": vault,
        "slug": slug,
        "vault_path": slug,
        "title": title,
        "note_type": "reference",
        "status": "stub",
        "tags": tags,
        "relevance": [],
        "summary": "",
        "body_markdown": body,
        "frontmatter": {"title": title, "tags": tags},
        "sources": [],
        "wikilinks": wikilinks,
    }


def _seed_filesystem(root: Path) -> FilesystemStore:
    (root / "a.md").write_text(
        "---\ntitle: A\ntags: [module]\n---\nlinks to [[b]] and [[c]]\n",
        encoding="utf-8",
    )
    (root / "b.md").write_text(
        "---\ntitle: B\ntags: [module, shipped]\n---\nlinks to [[c]]\n",
        encoding="utf-8",
    )
    (root / "c.md").write_text("---\ntitle: C\n---\nleaf note\n", encoding="utf-8")
    return FilesystemStore(root)


def _seed_postgres(*, vault: str = "finance") -> PostgresStore:
    client = _FakeClient()
    store = PostgresStore(client, vault=vault)
    store.create_note(
        "a", frontmatter={"title": "A", "tags": ["module"]}, body="links to [[b]] and [[c]]\n"
    )
    store.create_note(
        "b", frontmatter={"title": "B", "tags": ["module", "shipped"]}, body="links to [[c]]\n"
    )
    store.create_note("c", frontmatter={"title": "C"}, body="leaf note\n")
    return store


def test_filesystem_store_is_vault_store(tmp_path: Path) -> None:
    store = _seed_filesystem(tmp_path)
    assert isinstance(store, VaultStore)


def test_postgres_store_is_vault_store() -> None:
    store = _seed_postgres()
    assert isinstance(store, VaultStore)


@pytest.mark.parametrize("backend", ["filesystem", "postgres"])
def test_store_parity_reads(tmp_path: Path, backend: str) -> None:
    store: VaultStore
    if backend == "filesystem":
        store = _seed_filesystem(tmp_path)
    else:
        store = _seed_postgres()

    assert {n.name for n in store.list_notes()} == {"a", "b", "c"}
    assert store.backlinks("c") == ("a", "b")
    assert store.backlinks("b") == ("a",)
    assert [n.name for n in store.search_by_tag("shipped")] == ["b"]
    assert {n.name for n in store.search_by_tag("module")} == {"a", "b"}
    assert store.neighbors("c") == ("a", "b")
    assert store.neighbors("a") == ("b", "c")
    assert "[[b]]" in store.read_text("a")


@pytest.mark.parametrize("backend", ["filesystem", "postgres"])
def test_store_parity_writes(tmp_path: Path, backend: str) -> None:
    store: VaultStore
    if backend == "filesystem":
        store = _seed_filesystem(tmp_path)
    else:
        store = _seed_postgres()

    note = store.create_note(
        "d", frontmatter={"title": "D", "tags": ["x"]}, body="points at [[a]]\n"
    )
    assert note.name == "d"
    assert store.backlinks("a") == ("d",)
    assert "d" in store.neighbors("a")

    updated = store.set_frontmatter("d", {"status": "reviewed"})
    assert updated.frontmatter.get("status") == "reviewed"

    renamed = store.rename("c", "gamma")
    assert renamed.name == "gamma"
    assert {n.name for n in store.list_notes()} == {"a", "b", "d", "gamma"}
    assert "[[gamma]]" in store.read_text("a")
    assert store.backlinks("gamma") == ("a", "b")


def test_postgres_filters_by_vault_namespace() -> None:
    client = _FakeClient(
        [
            {
                "vault": "finance",
                "slug": "alpha",
                "vault_path": "alpha",
                "title": "Alpha",
                "note_type": "theory",
                "status": "stub",
                "tags": ["finance"],
                "relevance": [],
                "summary": "",
                "body_markdown": "see [[beta]]",
                "frontmatter": {"title": "Alpha", "tags": ["finance"]},
                "sources": [],
                "wikilinks": ["beta"],
            },
            {
                "vault": "product",
                "slug": "alpha",
                "vault_path": "alpha",
                "title": "Product Alpha",
                "note_type": "reference",
                "status": "stub",
                "tags": ["product"],
                "relevance": [],
                "summary": "",
                "body_markdown": "product only",
                "frontmatter": {"title": "Product Alpha", "tags": ["product"]},
                "sources": [],
                "wikilinks": [],
            },
        ]
    )
    finance = PostgresStore(client, vault="finance")
    product = PostgresStore(client, vault="product")
    assert [n.name for n in finance.list_notes()] == ["alpha"]
    assert finance.list_notes()[0].title == "Alpha"
    assert [n.name for n in product.list_notes()] == ["alpha"]
    assert product.list_notes()[0].title == "Product Alpha"
    # Graph from wikilinks column — unresolved target stays out of neighbors.
    assert finance.neighbors("alpha") == ()


def test_postgres_rejects_duplicate_create() -> None:
    store = _seed_postgres()
    with pytest.raises(VaultError):
        store.create_note("a")


def test_postgres_create_rejects_path_collision() -> None:
    client = _FakeClient(
        [
            {
                "vault": "finance",
                "slug": "old",
                "vault_path": "theory/x",
                "title": "Old",
                "note_type": "theory",
                "status": "stub",
                "tags": [],
                "relevance": [],
                "summary": "",
                "body_markdown": "old",
                "frontmatter": {"title": "Old"},
                "sources": [],
                "wikilinks": [],
            }
        ]
    )
    store = PostgresStore(client, vault="finance")
    with pytest.raises(VaultError, match="path already exists"):
        store.create_note("x", subdir="theory")
    assert [n.name for n in store.list_notes()] == ["old"]


def test_postgres_rejects_subdir_traversal() -> None:
    store = _seed_postgres()
    with pytest.raises(VaultError, match="escapes"):
        store.create_note("evil", subdir="../outside")


def test_postgres_relevance_string_not_char_split() -> None:
    store = _seed_postgres()
    store.create_note("rel", frontmatter={"title": "R", "relevance": "all"}, body="x\n")
    row = store._rows_by_name["rel"]
    assert row["relevance"] == ["all"]


def test_filesystem_neighbors(tmp_path: Path) -> None:
    store = _seed_filesystem(tmp_path)
    assert store.neighbors("missing") == ()
    assert store.neighbors("b") == ("a", "c")


_PAGE = 3
_SUPABASE_ENV = (
    "CORE_SUPABASE_URL",
    "SUPABASE_URL",
    "CORE_SUPABASE_ANON_KEY",
    "CORE_SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def _paged_rows() -> list[dict[str, Any]]:
    """Seven notes: page 1 is n00-n02 when page_size=3. n00 links to n06 (page 3)."""
    rows = [_note_row(f"n{i:02d}", body=f"body-{i:02d}") for i in range(7)]
    rows[0] = _note_row(
        "n00",
        body="see [[n06]]",
        tags=["hub"],
        wikilinks=["n06"],
    )
    rows[6] = _note_row("n06", body="leaf on last page", tags=["leaf"])
    return rows


def _clear_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _SUPABASE_ENV:
        monkeypatch.delenv(var, raising=False)


def _unsigned_jwt(role: str) -> str:
    def b64(payload: dict[str, str]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{b64({'alg': 'none'})}.{b64({'role': role})}.sig"


def test_postgres_reindex_indexes_every_row_across_postgrest_pages() -> None:
    client = _FakeClient(_paged_rows(), max_rows=_PAGE)
    store = PostgresStore(client, vault="finance", page_size=_PAGE)
    names = [n.name for n in store.list_notes()]
    assert names == [f"n{i:02d}" for i in range(7)]
    assert len(set(names)) == 7
    assert client.range_calls == [(0, 2), (3, 5), (6, 8)]


def test_postgres_reads_span_page_boundaries() -> None:
    store = PostgresStore(
        _FakeClient(_paged_rows(), max_rows=_PAGE), vault="finance", page_size=_PAGE
    )
    leaf = store.get_note("n06")
    assert leaf is not None
    assert "leaf on last page" in store.read_text("n06")
    assert store.backlinks("n06") == ("n00",)
    assert [n.name for n in store.search_by_tag("leaf")] == ["n06"]
    assert [n.name for n in store.search_by_tag("hub")] == ["n00"]


def _bodies_by_slug(client: _FakeClient) -> dict[str, str]:
    return {str(r["slug"]): str(r["body_markdown"]) for r in client._table.rows}


def test_postgres_rename_collision_beyond_page_one_does_not_lose_data() -> None:
    rows = _paged_rows()
    rows.append(_note_row("zzz", body="must survive"))
    rows.append(_note_row("hub", body="see [[n00]]", wikilinks=["n00"]))
    client = _FakeClient(rows, max_rows=_PAGE)
    store = PostgresStore(client, vault="finance", page_size=_PAGE)
    assert store.get_note("zzz") is not None
    with pytest.raises(VaultError, match="already exists"):
        store.rename("n00", "zzz")
    bodies = _bodies_by_slug(client)
    assert bodies["n00"] == "see [[n06]]"
    assert bodies["zzz"] == "must survive"
    assert "[[n00]]" in bodies["hub"]


def test_postgres_rename_does_not_overwrite_unindexed_destination() -> None:
    """A dest row omitted from the in-memory index must still be protected.

    Truncated reindex (or a race) plus upsert-on-conflict would clobber it (#3606).
    """
    client = _FakeClient(
        [
            _note_row("n00", body="move me"),
            _note_row("hub", body="see [[n00]]", wikilinks=["n00"]),
        ]
    )
    store = PostgresStore(client, vault="finance")
    client._table.rows.append(_note_row("zzz", body="must survive"))
    assert store.get_note("zzz") is None
    with pytest.raises(VaultError, match="already exists"):
        store.rename("n00", "zzz")
    bodies = _bodies_by_slug(client)
    assert bodies["n00"] == "move me"
    assert bodies["zzz"] == "must survive"
    assert "[[n00]]" in bodies["hub"]


@pytest.mark.parametrize("page_size", [0, -1])
def test_postgres_rejects_non_positive_page_size(page_size: int) -> None:
    with pytest.raises(ValueError, match=str(page_size)):
        PostgresStore(_FakeClient([]), vault="finance", page_size=page_size)


def test_postgres_from_env_rejects_anon_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("CORE_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("CORE_SUPABASE_ANON_KEY", "anon-placeholder")
    with pytest.raises(PostgresStoreError, match="service-role"):
        PostgresStore.from_env()


def test_postgres_from_env_rejects_anon_jwt_in_service_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("CORE_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("CORE_SUPABASE_SERVICE_KEY", _unsigned_jwt("anon"))
    with pytest.raises(PostgresStoreError, match="anon"):
        PostgresStore.from_env()


def test_postgres_from_env_requires_url_and_service_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_supabase_env(monkeypatch)
    with pytest.raises(PostgresStoreError, match="not configured"):
        PostgresStore.from_env()


def test_postgres_from_env_accepts_service_role_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("CORE_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("CORE_SUPABASE_SERVICE_KEY", _unsigned_jwt("service_role"))
    captured: dict[str, str] = {}

    def create_client(url: str, key: str) -> _FakeClient:
        captured["url"] = url
        captured["key"] = key
        return _FakeClient()

    fake_mod = types.ModuleType("supabase")
    fake_mod.create_client = create_client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "supabase", fake_mod)
    store = PostgresStore.from_env(vault="finance")
    assert captured["url"] == "https://example.supabase.co"
    assert captured["key"] == _unsigned_jwt("service_role")
    assert store.vault == "finance"
