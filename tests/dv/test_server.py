"""Service-layer tests. Skipped unless the [service] extra (fastapi/digikey) is installed."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from digivault.d1_errors import D1StoreError
from digivault.d1_store import D1Store
from digivault.models import NoteDetail
from digivault.orchestrator_tools import ORCHESTRATOR_TOOL_NAMES
from digivault.path_scopes import SCOPE_READ, SCOPE_WRITE
from digivault.supabase_store import SupabaseStore
from digivault.vault import Vault
from fastapi import HTTPException
from fastapi.testclient import TestClient

from digivault import server
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


def _fake_rl_request(
    ip: str = "203.0.113.5", headers: dict[str, str] | None = None
) -> SimpleNamespace:
    """Stand-in for a Starlette Request — only what `_rl_check` reads."""
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=ip),
        state=SimpleNamespace(),
    )


def _fake_request(scopes: list[str] | None = None) -> SimpleNamespace:
    """Stand-in for FastAPI's Request — only `.state.digi_auth.scopes` is read."""
    return SimpleNamespace(state=SimpleNamespace(digi_auth=SimpleNamespace(scopes=scopes or [])))


class _FakeSearchResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeSearchClient:
    """Minimal SupabaseClientProtocol stand-in — only `rpc().execute()` is exercised."""

    def __init__(self, rpc_data: list[dict]) -> None:
        self._rpc_data = rpc_data
        self.rpc_calls: list[tuple[str, dict]] = []

    def table(self, _name: str) -> None:  # pragma: no cover - search_notes never calls .table()
        raise AssertionError("digivault_search_notes must not touch the local table() path")

    def rpc(self, fn: str, params: dict) -> "_FakeSearchClient":
        self.rpc_calls.append((fn, params))
        return self

    def execute(self) -> _FakeSearchResponse:
        return _FakeSearchResponse(self._rpc_data)


@pytest.fixture
def vault_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "a.md").write_text(
        "---\ntitle: A\ntags: [doc]\n---\nlinks [[b]]\n", encoding="utf-8"
    )
    (tmp_path / "b.md").write_text("---\ntitle: B\n---\nleaf\n", encoding="utf-8")
    monkeypatch.setenv("DIGIVAULT_ROOT", str(tmp_path))
    return tmp_path


def test_healthz_is_public() -> None:
    resp = TestClient(server.app).get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_status_is_public() -> None:
    resp = TestClient(server.app).get("/v1/status")
    assert resp.status_code == 200
    assert resp.json()["service"] == "digivault"


def test_protected_route_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # No digikey configured -> middleware returns 503 auth_not_configured.
    monkeypatch.delenv("DIGIKEY_JWKS_URL", raising=False)
    monkeypatch.delenv("DIGIKEY_PUBLIC_KEY_PEM", raising=False)
    resp = TestClient(server.app).get("/v1/notes")
    assert resp.status_code == 503
    assert resp.json()["code"] == "auth_not_configured"


def test_list_and_create_handlers(vault_dir: Path) -> None:
    listing = server.list_notes()
    assert {n.name for n in listing.notes} == {"a", "b"}

    created = server.create_note(server.CreateNoteRequest(name="c", title="C", body="see [[a]]\n"))
    assert created.name == "c"
    assert (vault_dir / "c.md").is_file()

    backlinks = server.get_backlinks("a")
    assert "c" in backlinks.backlinks


def test_create_note_overwrite_upsert(vault_dir: Path) -> None:
    server.create_note(
        server.CreateNoteRequest(
            name="c",
            title="C1",
            body="v1\n",
            frontmatter={"source_url": "repo://t/a.md"},
        )
    )
    again = server.create_note(
        server.CreateNoteRequest(
            name="c",
            title="C2",
            body="v2\n",
            overwrite=True,
            frontmatter={"source_url": "repo://t/a.md", "page_class": "repo_doc"},
        )
    )
    assert again.name == "c"
    raw = (vault_dir / "c.md").read_text(encoding="utf-8")
    assert "v2" in raw
    assert "page_class" in raw


def test_lint_handler(vault_dir: Path) -> None:
    report = server.lint()
    assert report.ok is True
    assert report.note_count == 2


def test_orchestrator_tools_manifest() -> None:
    resp = server.orchestrator_tools()
    names = {t["function"]["name"] for t in resp.tools}
    assert names == ORCHESTRATOR_TOOL_NAMES


def test_orchestrator_invoke_search_tag(vault_dir: Path) -> None:
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_search_tag", arguments={"tag": "doc"}),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert [n["name"] for n in resp.data["notes"]] == ["a"]


def test_orchestrator_invoke_unknown_tool(vault_dir: Path) -> None:
    with pytest.raises(Exception):
        server.orchestrator_invoke(server.OrchestratorInvokeRequest(tool="nope"), _fake_request())


def test_orchestrator_invoke_create_note_requires_write_scope(vault_dir: Path) -> None:
    """The shared invoke endpoint is read-scoped; create_note enforces write itself."""
    with pytest.raises(HTTPException) as excinfo:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(tool="digivault_create_note", arguments={"name": "c"}),
            _fake_request(scopes=["digivault:read"]),
        )
    assert excinfo.value.status_code == 403


def test_orchestrator_invoke_create_note_succeeds_with_write_scope(vault_dir: Path) -> None:
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_create_note", arguments={"name": "c"}),
        _fake_request(scopes=[SCOPE_WRITE]),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data["name"] == "c"


def test_healthz_not_rate_limited_under_burst() -> None:
    client = TestClient(server.app)
    for _ in range(50):
        assert client.get("/healthz").status_code == 200


def test_testclient_traffic_bypasses_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """TestClient requests report client host 'testclient' — exempt so test suites stay green."""
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    client = TestClient(server.app)
    for _ in range(50):
        assert client.get("/v1/status").status_code == 200


def test_rl_check_blocks_after_limit_then_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    req = _fake_rl_request("203.0.113.9")

    for _ in range(3):
        assert server._rl_check(req, max_req=3, window=60) is None

    blocked = server._rl_check(req, max_req=3, window=60)
    assert blocked is not None
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after") == "60"
    body = json.loads(bytes(blocked.body))
    assert body["error"]["code"] == "rate_limit_exceeded"


def test_rl_check_is_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    ip_a = _fake_rl_request("203.0.113.10")
    ip_b = _fake_rl_request("203.0.113.11")

    assert server._rl_check(ip_a, max_req=1, window=60) is None
    # ip_a is now at its limit; ip_b has a fresh bucket.
    assert server._rl_check(ip_a, max_req=1, window=60) is not None
    assert server._rl_check(ip_b, max_req=1, window=60) is None


def test_rl_check_reads_x_forwarded_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)
    server._rl_windows.clear()
    req = _fake_rl_request("10.0.0.1", headers={"X-Forwarded-For": "203.0.113.20, 10.0.0.1"})
    assert server._rl_check(req, max_req=1, window=60) is None
    blocked = server._rl_check(req, max_req=1, window=60)
    assert blocked is not None
    # Second request from the same forwarded IP is blocked — proves the bucket
    # key is the forwarded address (203.0.113.20), not the proxy hop (10.0.0.1).
    assert server._rl_windows.get("203.0.113.20") is not None
    assert "10.0.0.1" not in server._rl_windows


def test_rl_check_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_DISABLE_RATE_LIMIT", "1")
    server._rl_windows.clear()
    req = _fake_rl_request("203.0.113.30")
    for _ in range(20):
        assert server._rl_check(req, max_req=1, window=60) is None


def test_orchestrator_invoke_search_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    """digivault_search_notes must work with no DIGIVAULT_ROOT — it reads Supabase, not disk."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    hit = {
        "vault_path": "digigraph",
        "title": "digigraph",
        "note_type": "module",
        "summary": "orchestration hub",
        "body_markdown": "LangGraph-based workflow engine.",
        "tags": ["core"],
        "wikilinks": [],
        "rank": 0.8,
    }
    fake_client = _FakeSearchClient(rpc_data=[hit])
    monkeypatch.setattr(server.SupabaseStore, "from_env", lambda: SupabaseStore(fake_client))

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "what does digigraph orchestrate", "limit": 3},
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data["hits"] == [
        {
            "vault_path": "digigraph",
            "title": "digigraph",
            "note_type": "module",
            "summary": "orchestration hub",
            "body_markdown": "LangGraph-based workflow engine.",
            "tags": ["core"],
            "wikilinks": [],
            "rank": 0.8,
        }
    ]
    assert fake_client.rpc_calls == [
        (
            "search_architecture_notes",
            {
                "query": "what does digigraph orchestrate",
                "match_limit": 3,
                "path_prefix": None,
            },
        )
    ]


def test_orchestrator_invoke_search_notes_local_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When DIGIVAULT_ROOT is set, search the local vault — never call Supabase."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    Vault(vault_root).create_note(
        "alpha-guide",
        frontmatter={"title": "Alpha onboarding", "tags": ["docs"]},
        body="Welcome to Alpha. Reset your password here.",
    )
    monkeypatch.setenv("DIGIVAULT_ROOT", str(vault_root))

    def _boom() -> SupabaseStore:
        raise AssertionError("local-root search must not open Supabase")

    monkeypatch.setattr(server.SupabaseStore, "from_env", _boom)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "alpha password", "limit": 5},
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    hits = resp.data["hits"]
    assert hits
    assert hits[0]["vault_path"].endswith("alpha-guide.md")
    assert hits[0]["rank"] > 0
    assert hits[0]["note_type"] == "local"


def test_orchestrator_invoke_search_notes_path_prefix_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """path_prefix keeps OCC / digithings corpora isolated under one vault root."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    Vault(vault_root).create_note(
        "faq-password",
        subdir="clients/online-compliance-center",
        frontmatter={"title": "OCC password FAQ"},
        body="OCC help: reset your portal password.",
    )
    Vault(vault_root).create_note(
        "architecture",
        subdir="clients/digithings",
        frontmatter={"title": "digithings architecture"},
        body="digigraph LangGraph orchestration hub password notes.",
    )
    monkeypatch.setenv("DIGIVAULT_ROOT", str(vault_root))

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={
                "query": "password",
                "limit": 10,
                "path_prefix": "clients/online-compliance-center",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    hits = resp.data["hits"]
    assert hits
    assert all("online-compliance-center" in h["vault_path"] for h in hits)
    assert not any(
        h["vault_path"].startswith("clients/digithings")
        or "/clients/digithings/" in f"/{h['vault_path']}"
        for h in hits
    )


def test_orchestrator_invoke_search_notes_default_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    fake_client = _FakeSearchClient(rpc_data=[])
    monkeypatch.setattr(server.SupabaseStore, "from_env", lambda: SupabaseStore(fake_client))

    server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes", arguments={"query": "auth", "limit": "not-a-number"}
        ),
        _fake_request(),
    )
    assert fake_client.rpc_calls == [
        ("search_architecture_notes", {"query": "auth", "match_limit": 7, "path_prefix": None})
    ]


def test_orchestrator_invoke_search_notes_clamps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    fake_client = _FakeSearchClient(rpc_data=[])
    monkeypatch.setattr(server.SupabaseStore, "from_env", lambda: SupabaseStore(fake_client))

    server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes", arguments={"query": "auth", "limit": 5000}
        ),
        _fake_request(),
    )
    assert fake_client.rpc_calls == [
        ("search_architecture_notes", {"query": "auth", "match_limit": 50, "path_prefix": None})
    ]

    fake_client_negative = _FakeSearchClient(rpc_data=[])
    monkeypatch.setattr(
        server.SupabaseStore, "from_env", lambda: SupabaseStore(fake_client_negative)
    )
    server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes", arguments={"query": "auth", "limit": -3}
        ),
        _fake_request(),
    )
    assert fake_client_negative.rpc_calls == [
        ("search_architecture_notes", {"query": "auth", "match_limit": 1, "path_prefix": None})
    ]


def test_orchestrator_invoke_search_notes_missing_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_search_notes", arguments={"query": "   "}),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "query is required"


def test_orchestrator_invoke_search_notes_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    for var in (
        "CORE_SUPABASE_URL",
        "SUPABASE_URL",
        "CORE_SUPABASE_ANON_KEY",
        "CORE_SUPABASE_SERVICE_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(HTTPException) as excinfo:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes", arguments={"query": "hello"}
            ),
            _fake_request(),
        )
    assert excinfo.value.status_code == 503


# ── D1 backend precedence (#2239) ────────────────────────────────────────────
def _set_d1_env(monkeypatch: pytest.MonkeyPatch, database_map: str) -> None:
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", database_map)


def test_open_d1_store_raises_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store("clients/digithings")
    assert "D1_ACCOUNT_ID" in str(exc.value)


def test_open_d1_store_raises_when_prefix_has_no_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store("clients/other")
    assert "clients/other" in str(exc.value)


def test_open_d1_store_builds_store_scoped_to_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    store = server._open_d1_store("clients/digithings")
    assert isinstance(store, D1Store)
    assert store.database_id == "db-1"


def test_open_d1_store_rejects_empty_string_map_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """#2239 review, Critical finding: a "" entry in D1_DATABASE_MAP would map every
    prefix that normalizes to empty (None, "", "/", "///", "   ", ".md") to a real
    database, arming the by-path route's cross-tenant fail-open. Refused at
    config-read time regardless of which prefix was requested."""
    _set_d1_env(monkeypatch, '{"": "db-unscoped", "clients/digithings": "db-1"}')
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store(None)
    assert "D1_DATABASE_MAP" in str(exc.value)
    # The guard fires for every call, not just the one requesting the "" prefix.
    with pytest.raises(D1StoreError):
        server._open_d1_store("clients/digithings")


def test_open_d1_store_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_d1_env(monkeypatch, "{not json")
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store("clients/digithings")
    assert "not valid JSON" in str(exc.value)


def test_open_d1_store_rejects_non_object_database_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1_DATABASE_MAP must be a JSON object; a list must not crash with AttributeError."""
    _set_d1_env(monkeypatch, '["clients/digithings"]')
    with pytest.raises(D1StoreError):
        server._open_d1_store("clients/digithings")


def test_open_d1_store_or_503_converts_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(HTTPException) as exc:
        server._open_d1_store_or_503("clients/digithings")
    assert exc.value.status_code == 503


def test_orchestrator_invoke_search_notes_prefers_d1_even_with_digivault_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D1 must win even when DIGIVAULT_ROOT is set — the #2239 production bug: prod's
    baked /data/vault seed stubs must never shadow the real D1-backed corpus."""
    monkeypatch.setenv("DIGIVAULT_ROOT", "/data/vault")  # must NOT win
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    called: dict = {}

    class _FakeD1:
        def search(self, query: str, *, limit: int, path_prefix: str | None) -> list:
            called["args"] = (query, limit, path_prefix)
            return []

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "jwt", "limit": 3, "path_prefix": "clients/digithings"},
        ),
        _fake_request(),
    )
    assert called["args"] == ("jwt", 3, "clients/digithings")
    assert resp.ok is True
    assert resp.data == {"hits": []}


def test_orchestrator_invoke_search_notes_empty_path_prefix_stays_unscoped_for_d1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 1 review: D1Store.search raises ValueError for path_prefix="" (distinct from
    None). server.py's existing `... or None` coalescing must survive unmodified, or an
    empty caller-supplied path_prefix starts returning HTTP 500 through the D1 path too."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    called: dict = {}

    class _FakeD1:
        def search(self, query: str, *, limit: int, path_prefix: str | None) -> list:
            called["path_prefix"] = path_prefix
            return []

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "jwt", "path_prefix": ""},
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert called["path_prefix"] is None


def test_orchestrator_invoke_search_notes_d1_misconfigured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D1 configured but the requested prefix has no database -> 503, not a raw 500."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={"query": "jwt", "path_prefix": "clients/other"},
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503


def test_orchestrator_invoke_search_notes_d1_unscoped_returns_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review, Important finding: `always_retrieve_tools` fires
    `digivault_search_notes` with no `path_prefix` on every chat turn (#2265). With D1
    configured there is no "search every corpus" mode, so this must be an actionable
    400 telling the caller `path_prefix` is required — not a 503 that reads like a
    missing config entry an operator could "fix" with a `""` map key (refused
    separately by `_open_d1_store`'s own guard)."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes", arguments={"query": "jwt"}
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 400
    assert "path_prefix is required" in str(exc.value.detail)


def test_orchestrator_invoke_search_notes_d1_runtime_failure_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review, Important finding: a D1StoreError raised from *inside* `.search()`
    (transport failure, expired token) must still become 503, not an unhandled 500 —
    `_open_d1_store_or_503` only wrapped construction, not this call."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')

    class _FakeD1:
        def search(self, query: str, *, limit: int, path_prefix: str | None) -> list:
            raise D1StoreError("d1 search transport failure: boom")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={"query": "jwt", "path_prefix": "clients/digithings"},
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503
    assert "transport failure" in str(exc.value.detail)


# ── by-path note fetch (#2239) ───────────────────────────────────────────────
def test_get_note_by_path_returns_404_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeD1:
        def get_note(self, vault_path: str) -> None:
            return None

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(server.NoteByPathRequest(vault_path="clients/digithings/nope"))
    assert exc.value.status_code == 404


def test_get_note_by_path_enforces_the_caller_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller scoped to digithings must not read the OCC corpus by guessing a path."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/online-compliance-center/x",
                path_prefix="clients/digithings",
            )
        )
    assert exc.value.status_code == 403


def test_get_note_by_path_allows_exact_prefix_match(monkeypatch: pytest.MonkeyPatch) -> None:
    """vault_path == path_prefix is in-scope, not just paths strictly under it."""
    note = NoteDetail(vault_path="clients/digithings", title="root", body_markdown="hi")

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail | None:
            return note if vault_path == "clients/digithings" else None

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    result = server.get_note_by_path(
        server.NoteByPathRequest(vault_path="clients/digithings", path_prefix="clients/digithings")
    )
    assert result is note


def test_get_note_by_path_returns_note_scoped_to_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hi")
    called: dict = {}

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail | None:
            called["vault_path"] = vault_path
            return note

    def _open(prefix: str | None) -> _FakeD1:
        called["prefix"] = prefix
        return _FakeD1()

    monkeypatch.setattr(server, "_open_d1_store", _open)
    result = server.get_note_by_path(
        server.NoteByPathRequest(
            vault_path="clients/digithings/arch", path_prefix="clients/digithings"
        )
    )
    assert result is note
    assert called["prefix"] == "clients/digithings"
    assert called["vault_path"] == "clients/digithings/arch"


def test_get_note_by_path_without_prefix_opens_store_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict = {}

    class _FakeD1:
        def get_note(self, vault_path: str) -> None:
            return None

    def _open(prefix: str | None) -> _FakeD1:
        called["prefix"] = prefix
        return _FakeD1()

    monkeypatch.setattr(server, "_open_d1_store", _open)
    with pytest.raises(HTTPException):
        server.get_note_by_path(server.NoteByPathRequest(vault_path="clients/digithings/nope"))
    assert called["prefix"] is None


def test_get_note_by_path_returns_503_when_d1_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(server.NoteByPathRequest(vault_path="clients/digithings/x"))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("bad_prefix", ["", "/", "///", "   ", ".md"])
def test_get_note_by_path_rejects_prefix_that_normalizes_to_empty(
    monkeypatch: pytest.MonkeyPatch, bad_prefix: str
) -> None:
    """Critical #2239 review finding: `if prefix and ...` treated "a prefix was given
    but normalizes to empty" as "no scoping requested" — fail-open. The reviewer
    demonstrated that with a "" key present in D1_DATABASE_MAP, every one of these
    inputs returned another corpus's note body with HTTP 200. Now rejected with 400
    before the store is even opened (`_open_d1_store` is never called — asserted via
    the fake store raising if it is), mirroring `resolve_path_prefix`'s semantics."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for an empty-ish prefix")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/other-corpus/secret", path_prefix=bad_prefix
            )
        )
    assert exc.value.status_code == 400


def test_get_note_by_path_wraps_runtime_d1_error_as_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """#2239 review, Important finding: a D1StoreError raised from *inside*
    `.get_note()` (transport failure, or Cloudflare's real 403 on an expired
    D1_API_TOKEN) must become 503, not an unhandled 500 — `_open_d1_store_or_503`
    only wrapped construction, not this call."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise D1StoreError("d1 get_note failed (403): Authentication error")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(server.NoteByPathRequest(vault_path="clients/digithings/x"))
    assert exc.value.status_code == 503
    assert "Authentication error" in str(exc.value.detail)


def test_note_by_path_route_is_read_scoped_despite_being_post() -> None:
    """POST /v1/notes/by-path is a read (fetch), not a mutation — must not require write."""
    assert server.digivault_path_scopes("POST", "/v1/notes/by-path") == [SCOPE_READ]


def test_note_by_path_carve_out_is_method_aware() -> None:
    """Minor #2239 review finding: the carve-out matched on path alone, ignoring
    method — only POST is registered today (everything else 405s), but a bare path
    match would silently read-scope a future DELETE/PUT on the same literal path."""
    assert server.digivault_path_scopes("DELETE", "/v1/notes/by-path") == [SCOPE_WRITE]
    assert server.digivault_path_scopes("PUT", "/v1/notes/by-path") == [SCOPE_WRITE]


def test_by_path_route_is_not_shadowed_by_the_name_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A POST to /v1/notes/by-path must reach the new handler, not GET /v1/notes/{name}."""
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hi")

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            return note

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    client = TestClient(server.app)

    posted = client.post(
        "/v1/notes/by-path",
        json={"vault_path": "clients/digithings/arch"},
        headers=auth_headers(scopes=[SCOPE_READ]),
    )
    assert posted.status_code == 200
    assert posted.json()["vault_path"] == "clients/digithings/arch"

    # GET on the same literal path must still resolve to the {name} route (name="by-path",
    # via _open_vault -> DIGIVAULT_ROOT), proving the two routes coexist rather than one
    # shadowing the other. Its 503 message is distinct from the D1-store-unconfigured
    # message the by-path POST handler would raise, so this pins *which* handler answered.
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    got = client.get("/v1/notes/by-path", headers=auth_headers(scopes=[SCOPE_READ]))
    assert got.status_code == 503
    assert got.json()["error"]["message"] == "DIGIVAULT_ROOT is not configured"
