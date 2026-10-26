"""digivault tag/backlink lookups answer from the same D1 corpus as get_note, and
in-container loopback callers do not share one per-IP rate-limit bucket.

Mocked only: D1 is stood in by an in-memory SQLite database running the real
schema and the store's real SQL (D1 is SQLite). No network, no Cloudflare.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from digivault.d1_store import D1Store

from digivault import server

pytestmark = pytest.mark.unit

SCHEMA = Path(server.__file__).with_name("d1_schema.sql").read_text()
PREFIX = "clients/acme"


class _SqliteD1(D1Store):
    """D1Store whose transport is a local SQLite connection (same SQL dialect)."""

    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.ops: list[str] = []

    def query(self, sql: str, params: list[Any], *, operation: str) -> list[dict[str, Any]]:
        self.ops.append(operation)
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def add(
        self, path: str, *, tags: list[str] = (), links: list[str] = (), title: str = ""
    ) -> None:
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(notes)")}
        row = {
            "vault_path": path,
            "title": title or path.rsplit("/", 1)[-1],
            "body": "b",
            "tags": json.dumps(list(tags)),
            "wikilinks": json.dumps(list(links)),
        }
        row = {k: v for k, v in row.items() if k in cols}
        self.db.execute(
            f"INSERT INTO notes ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
            list(row.values()),
        )


@pytest.fixture
def store() -> _SqliteD1:
    s = _SqliteD1()
    s.add(f"{PREFIX}/manual/reset-password", tags=["Portal", "#how-to"], title="Reset password")
    s.add(f"{PREFIX}/manual/login", tags=["portal"], links=["[[reset-password|reset it]]"])
    s.add(f"{PREFIX}/faq/accounts", links=["manual/reset-password#steps", "other"])
    s.add(f"{PREFIX}/faq/unrelated", tags=["billing"], links=["[[login]]"])
    s.add("clients/other/secret", tags=["portal"], links=["[[reset-password]]"])
    return s


def _req(tenant: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(digi_auth=SimpleNamespace(scopes=[], tenant_slug=tenant))
    )


def _invoke(monkeypatch: pytest.MonkeyPatch, store: _SqliteD1, tool: str, args: dict) -> Any:
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", json.dumps({PREFIX: "db-1"}))
    monkeypatch.setenv("DIGIVAULT_ROOT", "/nonexistent-filesystem-vault")  # must not be read
    monkeypatch.setattr(server, "_open_d1_store_or_503", lambda prefix: store)
    monkeypatch.setattr(
        server, "_open_scoped_vault", lambda request: pytest.fail("filesystem vault used")
    )
    return server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool=tool, arguments=args), _req()
    )


# ── tags ────────────────────────────────────────────────────────────────────
def test_search_tag_reads_d1_case_insensitive_and_hash_optional(monkeypatch, store) -> None:
    resp = _invoke(
        monkeypatch, store, "digivault_search_tag", {"tag": "#PORTAL", "path_prefix": PREFIX}
    )
    assert resp.ok is True
    paths = [n["vault_path"] for n in resp.data["notes"]]
    assert paths == [f"{PREFIX}/manual/login", f"{PREFIX}/manual/reset-password"]
    assert "clients/other/secret" not in paths  # sibling corpus never leaks


def test_search_tag_is_exact_not_substring(monkeypatch, store) -> None:
    resp = _invoke(
        monkeypatch, store, "digivault_search_tag", {"tag": "port", "path_prefix": PREFIX}
    )
    assert resp.ok is True and resp.data["notes"] == []


def test_search_tag_requires_prefix_on_d1(monkeypatch, store) -> None:
    resp = _invoke(monkeypatch, store, "digivault_search_tag", {"tag": "portal"})
    assert resp.ok is False and "path_prefix is required" in resp.error


# ── backlinks resolve names like get_note ────────────────────────────────────
@pytest.mark.parametrize(
    "name",
    [
        f"{PREFIX}/manual/reset-password",  # the vault_path get_note takes
        f"{PREFIX}/manual/reset-password.md",  # with .md, as get_note normalises
        f"/{PREFIX}/manual/reset-password/",  # stray slashes
        "reset-password",  # bare stem (the manifest's "name")
    ],
)
def test_backlinks_accept_every_get_note_spelling(monkeypatch, store, name) -> None:
    resp = _invoke(monkeypatch, store, "digivault_backlinks", {"name": name, "path_prefix": PREFIX})
    assert resp.ok is True, resp.error
    assert resp.data["name"] == f"{PREFIX}/manual/reset-password"
    assert resp.data["backlinks"] == [f"{PREFIX}/faq/accounts", f"{PREFIX}/manual/login"]


def test_backlinks_outside_prefix_reads_as_missing(monkeypatch, store) -> None:
    resp = _invoke(
        monkeypatch,
        store,
        "digivault_backlinks",
        {"name": "clients/other/secret", "path_prefix": PREFIX},
    )
    assert resp.ok is False and resp.error.startswith("No such note")


def test_backlinks_ambiguous_stem_does_not_guess(monkeypatch, store) -> None:
    store.add(f"{PREFIX}/faq/login")
    resp = _invoke(
        monkeypatch, store, "digivault_backlinks", {"name": "login", "path_prefix": PREFIX}
    )
    assert resp.ok is False and resp.error.startswith("No such note")


def test_backlinks_unknown_note(monkeypatch, store) -> None:
    resp = _invoke(
        monkeypatch, store, "digivault_backlinks", {"name": "nope", "path_prefix": PREFIX}
    )
    assert resp.ok is False and resp.error.startswith("No such note")


def test_without_d1_the_filesystem_path_is_unchanged(monkeypatch) -> None:
    called = {}
    monkeypatch.setattr(
        server, "_open_scoped_vault", lambda request: called.setdefault("fs", object())
    )
    monkeypatch.setattr(
        server,
        "dispatch_vault_tool",
        lambda tool, args, vault: SimpleNamespace(ok=True, data={"notes": []}, error=None),
    )
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_search_tag", arguments={"tag": "x"}),
        _req(),
    )
    assert resp.ok is True and "fs" in called
    # The filesystem vault has no scan cap, so the same envelope reports false.
    assert resp.data["truncated"] is False


# ── truncation is reported, the lists themselves do not change ───────────────
def _tag_candidates(store: _SqliteD1, count: int, tag: str) -> None:
    for i in range(count):
        store.add(f"{PREFIX}/bulk/t{i:04d}", tags=[tag])


def test_search_tag_reports_the_candidate_cap(monkeypatch, store) -> None:
    """801 rows match the SQL prefilter but not the exact tag: the 800 cap was hit."""
    _tag_candidates(store, 801, "bulkish")
    resp = _invoke(
        monkeypatch, store, "digivault_search_tag", {"tag": "bulk", "path_prefix": PREFIX}
    )
    assert resp.ok is True
    assert resp.data["truncated"] is True
    assert resp.data["notes"] == []  # the list is still exact-match only


def test_search_tag_at_the_candidate_cap_is_not_truncated(monkeypatch, store) -> None:
    """Exactly 800 candidates fit the scan, so the answer is complete."""
    _tag_candidates(store, 800, "bulkish")
    resp = _invoke(
        monkeypatch, store, "digivault_search_tag", {"tag": "bulk", "path_prefix": PREFIX}
    )
    assert resp.ok is True
    assert resp.data["truncated"] is False
    assert resp.data["notes"] == []


def test_search_tag_reports_the_return_cap(monkeypatch, store) -> None:
    """201 exact matches, 200 returned: the list is unchanged and says it was cut."""
    _tag_candidates(store, 201, "bulk")
    resp = _invoke(
        monkeypatch, store, "digivault_search_tag", {"tag": "bulk", "path_prefix": PREFIX}
    )
    assert resp.ok is True
    assert resp.data["truncated"] is True
    assert len(resp.data["notes"]) == 200


def _backlink_sources(store: _SqliteD1, count: int) -> None:
    store.add(f"{PREFIX}/cap-target", title="Target")
    for i in range(count):
        store.add(f"{PREFIX}/src/s{i:04d}", links=["[[cap-target]]"])


def test_backlinks_report_the_row_cap(monkeypatch, store) -> None:
    _backlink_sources(store, 501)
    resp = _invoke(
        monkeypatch, store, "digivault_backlinks", {"name": "cap-target", "path_prefix": PREFIX}
    )
    assert resp.ok is True, resp.error
    assert resp.data["truncated"] is True
    assert len(resp.data["backlinks"]) == 500  # the cap, not the 501st row


def test_backlinks_at_the_row_cap_are_not_truncated(monkeypatch, store) -> None:
    _backlink_sources(store, 500)
    resp = _invoke(
        monkeypatch, store, "digivault_backlinks", {"name": "cap-target", "path_prefix": PREFIX}
    )
    assert resp.ok is True, resp.error
    assert resp.data["truncated"] is False
    assert len(resp.data["backlinks"]) == 500


# ── rate limit: in-container loopback callers are exempt ─────────────────────
def _rl_req(ip: str, xff: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        headers={"X-Forwarded-For": xff} if xff else {},
        client=SimpleNamespace(host=ip),
        state=SimpleNamespace(),
    )


@pytest.mark.parametrize("ip", ["127.0.0.1", "127.0.0.9", "::1", "localhost"])
def test_loopback_without_forwarded_for_is_never_limited(monkeypatch, ip) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    for _ in range(50):
        assert server._rl_check(_rl_req(ip), max_req=10, window=60) is None


def test_loopback_with_forwarded_for_keeps_per_client_limit(monkeypatch) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    req = _rl_req("127.0.0.1", xff="198.51.100.7")
    for _ in range(2):
        assert server._rl_check(req, max_req=2, window=60) is None
    blocked = server._rl_check(req, max_req=2, window=60)
    assert blocked is not None and blocked.status_code == 429


def test_remote_peer_still_limited(monkeypatch) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    req = _rl_req("203.0.113.40")
    assert server._rl_check(req, max_req=1, window=60) is None
    assert server._rl_check(req, max_req=1, window=60) is not None
