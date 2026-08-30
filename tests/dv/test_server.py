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
from pydantic import ValidationError

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


def _fake_request(
    scopes: list[str] | None = None, tenant_slug: str | None = None
) -> SimpleNamespace:
    """Stand-in for FastAPI's Request — only `.state.digi_auth.scopes`/`.tenant_slug`
    are read (by `_require_tool_scope`/`_tenant_slug` respectively)."""
    return SimpleNamespace(
        state=SimpleNamespace(
            digi_auth=SimpleNamespace(scopes=scopes or [], tenant_slug=tenant_slug)
        )
    )


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


def test_batch_note_upsert_is_exposed_by_openapi() -> None:
    paths = server.app.openapi()["paths"]
    assert "/v1/notes/batch" in paths
    assert "post" in paths["/v1/notes/batch"]


def test_batch_note_upsert_keeps_links_consistent(vault_dir: Path) -> None:
    result = server.create_notes_batch(
        server.CreateNotesBatchRequest(
            notes=[
                server.CreateNoteRequest(name="c", body="see [[d]]\n"),
                server.CreateNoteRequest(name="d", body="see [[c]]\n"),
            ]
        )
    )

    assert [note.name for note in result.notes] == ["c", "d"]
    assert server.get_backlinks("c").backlinks == ["d"]
    assert server.get_backlinks("d").backlinks == ["c"]


def test_prune_children_handler_deletes_only_stale_children(vault_dir: Path) -> None:
    vault = Vault(vault_dir)
    vault.write_note(
        "guide__stale",
        frontmatter={"parent_doc": "guide"},
        body="stale\n",
        subdir="clients/acme",
    )
    vault.write_note(
        "guide__current",
        frontmatter={"parent_doc": "guide"},
        body="current\n",
        subdir="clients/acme",
    )
    vault.write_note(
        "other__stale",
        frontmatter={"parent_doc": "other"},
        body="keep\n",
        subdir="clients/acme",
    )

    result = server.prune_children(
        server.PruneChildrenRequest(
            parent_doc="guide",
            keep_names=["guide__current"],
            subdir="clients/acme",
        )
    )

    assert result.deleted == ["guide__stale"]
    assert Vault(vault_dir).get_note("guide__stale") is None
    assert Vault(vault_dir).get_note("guide__current") is not None
    assert Vault(vault_dir).get_note("other__stale") is not None


def test_lint_handler(vault_dir: Path) -> None:
    report = server.lint()
    assert report.ok is True
    assert report.note_count == 2


def test_orchestrator_tools_manifest() -> None:
    resp = server.orchestrator_tools()
    names = {t["function"]["name"] for t in resp.tools}
    assert names == ORCHESTRATOR_TOOL_NAMES


@pytest.mark.parametrize("tool_name", sorted(ORCHESTRATOR_TOOL_NAMES))
def test_every_advertised_orchestrator_tool_actually_dispatches(
    tool_name: str, vault_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2239 review, Minor M6: `test_orchestrator_tools_manifest` above only asserts
    that the *names* advertised by `POST /v1/orchestrator_tools` equal
    `ORCHESTRATOR_TOOL_NAMES` — it says nothing about whether `orchestrator_invoke`
    actually has a dispatch branch for each one. Commit cf61b673d shipped
    `digivault_get_note` in the manifest with no dispatch branch at all, and that test
    still passed happily; every real call to that tool 400'd with "Unknown
    orchestrator tool". Call every advertised tool with no arguments and assert none
    of them falls through to that specific `else` branch — any other outcome (ok=True,
    ok=False from a missing-argument check, even a raised HTTPException for some other
    reason) proves the tool was recognized; only that one message proves it was not."""
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    try:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(tool=tool_name, arguments={}),
            _fake_request(scopes=[SCOPE_READ, SCOPE_WRITE]),
        )
    except HTTPException as exc:
        assert "Unknown orchestrator tool" not in str(exc.detail)


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


# ── D1 partial-configuration guard (#2239 second review, Important finding) ─────
def test_d1_configured_false_when_all_three_vars_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero D1 vars set is a legitimate profile (local dev, self-hosted, Profile A)
    and must keep returning False, not raise."""
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    assert server._d1_configured() is False


def test_d1_configured_true_when_all_three_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    assert server._d1_configured() is True


# ── canonical CLOUDFLARE_*/legacy VECTORIZE_*/D1_* credential fallback (#2239
# credential rename) ─────────────────────────────────────────────────────────
def test_d1_configured_true_with_canonical_cloudflare_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """The canonical (wrangler-conventional) names alone must configure D1 -- no
    legacy VECTORIZE_*/D1_* name needs to be set at all."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')
    assert server._d1_configured() is True


def test_d1_configured_true_with_legacy_vectorize_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-downtime property: the deployed Worker's live VECTORIZE_ACCOUNT_ID/
    VECTORIZE_API_TOKEN secrets (same account + token as D1, per #2239) must keep
    activating D1 with no CLOUDFLARE_*/D1_* name set at all."""
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')
    assert server._d1_configured() is True


def test_open_d1_store_canonical_wins_over_legacy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """When multiple names in the fallback chain are set to *different* values, the
    canonical CLOUDFLARE_* pair must win over both legacy VECTORIZE_* and D1_*."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "canonical-acct")
    monkeypatch.setenv("VECTORIZE_ACCOUNT_ID", "legacy-vectorize-acct")
    monkeypatch.setenv("D1_ACCOUNT_ID", "legacy-d1-acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "canonical-tok")
    monkeypatch.setenv("VECTORIZE_API_TOKEN", "legacy-vectorize-tok")
    monkeypatch.setenv("D1_API_TOKEN", "legacy-d1-tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')

    captured: dict[str, str] = {}

    class _CapturingD1Store(D1Store):
        def __init__(self, database_id: str, *, account_id: str, api_token: str) -> None:
            captured["account_id"] = account_id
            captured["api_token"] = api_token
            super().__init__(database_id, account_id=account_id, api_token=api_token)

    monkeypatch.setattr(server, "D1Store", _CapturingD1Store)

    server._open_d1_store("clients/digithings")

    assert captured == {"account_id": "canonical-acct", "api_token": "canonical-tok"}


@pytest.mark.parametrize(
    ("missing_legacy_var", "expected_canonical_name"),
    [
        ("D1_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"),
        ("D1_API_TOKEN", "CLOUDFLARE_API_TOKEN"),
        ("D1_DATABASE_MAP", "D1_DATABASE_MAP"),
    ],
)
def test_d1_configured_raises_when_exactly_one_var_missing(
    monkeypatch: pytest.MonkeyPatch, missing_legacy_var: str, expected_canonical_name: str
) -> None:
    """#2239 second review, Important finding: with any two of three D1 vars set,
    `_d1_configured` used to return False -- indistinguishable from the legitimate
    zero-vars case -- and `orchestrator_invoke` fell through to the `elif
    DIGIVAULT_ROOT` branch, which production always sets to the baked /data/vault
    seed. That silently served seed stubs instead of the real corpus: HTTP 200,
    `ok: true`, nothing logged, reachable from a single typo'd secret name during
    cutover (`wrangler secret put D1_API_TOKN` -> `D1_API_TOKEN` undefined). Partial
    config has no legitimate reading, so this must raise, naming what's missing.

    Post-#2239-rename: the error names the *canonical* var (`CLOUDFLARE_ACCOUNT_ID`/
    `CLOUDFLARE_API_TOKEN`), not whichever legacy alias (`D1_ACCOUNT_ID`/
    `D1_API_TOKEN`) was actually deleted here -- the credential is resolved to one
    value by `_d1_credentials` before this guard ever runs, so "missing" always
    means "nothing in the fallback chain resolved," and the message must point the
    operator at the name to set going forward."""
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    monkeypatch.delenv(missing_legacy_var, raising=False)
    with pytest.raises(D1StoreError) as exc:
        server._d1_configured()
    assert expected_canonical_name in str(exc.value)


@pytest.mark.parametrize(
    ("missing_legacy_var", "expected_canonical_name"),
    [
        ("D1_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"),
        ("D1_API_TOKEN", "CLOUDFLARE_API_TOKEN"),
        ("D1_DATABASE_MAP", "D1_DATABASE_MAP"),
    ],
)
def test_orchestrator_invoke_search_notes_partial_d1_config_503s_not_seed_hits(
    monkeypatch: pytest.MonkeyPatch,
    vault_dir: Path,
    missing_legacy_var: str,
    expected_canonical_name: str,
) -> None:
    """Reproduces the reviewer's exact repro against a real seed vault
    (`vault_dir` sets DIGIVAULT_ROOT, same as production's baked stub): with D1
    missing exactly one of its three vars, this must 503 -- naming the missing
    (canonical) var -- rather than silently falling through to DIGIVAULT_ROOT and
    returning HTTP 200 with hits from the seed vault (#2239's precise symptom)."""
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    monkeypatch.delenv(missing_legacy_var, raising=False)

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes", arguments={"query": "links"}
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503
    assert expected_canonical_name in str(exc.value.detail)


def test_orchestrator_invoke_search_notes_partial_d1_config_503s_via_http(
    monkeypatch: pytest.MonkeyPatch, vault_dir: Path
) -> None:
    """HTTP-level version of the same repro, through the actual TestClient/route --
    matching how the reviewer reproduced it -- rather than calling the handler
    function directly."""
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    monkeypatch.delenv("D1_API_TOKEN", raising=False)

    client = TestClient(server.app)
    resp = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digivault_search_notes", "arguments": {"query": "links"}},
        headers=auth_headers(scopes=[SCOPE_READ]),
    )
    assert resp.status_code == 503
    assert "CLOUDFLARE_API_TOKEN" in resp.json()["error"]["message"]


def test_status_reports_d1_configured_true(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    resp = TestClient(server.app).get("/v1/status")
    assert resp.status_code == 200
    assert resp.json()["d1_configured"] is True


def test_status_reports_d1_configured_false_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    resp = TestClient(server.app).get("/v1/status")
    assert resp.status_code == 200
    assert resp.json()["d1_configured"] is False


@pytest.mark.parametrize("missing_var", ["D1_ACCOUNT_ID", "D1_API_TOKEN", "D1_DATABASE_MAP"])
def test_status_reports_d1_configured_false_on_partial_config_not_503(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    """The diagnostic route itself must never 503 on a partial D1 config -- that
    would defeat the point of letting an operator see backend state without
    asking the chat a question."""
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    monkeypatch.delenv(missing_var, raising=False)
    resp = TestClient(server.app).get("/v1/status")
    assert resp.status_code == 200
    assert resp.json()["d1_configured"] is False


def test_open_d1_store_raises_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store("clients/digithings")
    assert "CLOUDFLARE_ACCOUNT_ID" in str(exc.value)


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


def test_orchestrator_invoke_search_notes_empty_path_prefix_still_requires_prefix_for_d1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 second review, Important finding (row 1 of the 5-row matrix): a healthy
    `D1_DATABASE_MAP` plus an empty-ish caller-supplied `path_prefix` (`""`) must never
    reach the store unscoped. The invariant this pins is that it short-circuits before
    the store is even opened; it used to succeed unscoped whenever the fake store
    happened not to raise, because the check only fired inside an `except D1StoreError`.

    The *shape* of the rejection changed with the #2407 follow-up and again in
    #2408: a present-but-empty prefix now returns ok=False (HTTP 200) at the
    endpoint, matching digivault_get_note — not a raised 400 that digigraph's
    raise_for_status() would strip to a bare status code."""
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
    assert resp.ok is False
    assert "normalizes to empty" in (resp.error or "")
    assert called == {}  # _open_d1_store must never be reached


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


def test_orchestrator_invoke_search_notes_d1_unscoped_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review, Important finding (row 1): `always_retrieve_tools` fires
    `digivault_search_notes` with no `path_prefix` on every chat turn (#2265). With D1
    configured there is no "search every corpus" mode, so this must be an actionable
    `ok=False` telling the caller `path_prefix` is required — returned as
    `OrchestratorInvokeResponse`, HTTP 200, not raised as an HTTPException: a raised
    400 would reach digigraph's `invoke_digivault_tool` via `raise_for_status()`, whose
    `str(httpx.HTTPStatusError)` drops the response body, so the model would only ever
    see a bare status code, not this sentence (second #2239 review)."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_search_notes", arguments={"query": "jwt"}),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "path_prefix is required when the D1 backend is configured"


@pytest.mark.parametrize(
    "database_map",
    ["{not json", '["clients/digithings"]', '{"": "db-unscoped", "clients/digithings": "db-1"}'],
    ids=["invalid_json", "non_object", "empty_string_key"],
)
def test_orchestrator_invoke_search_notes_d1_config_error_returns_503_even_without_prefix(
    monkeypatch: pytest.MonkeyPatch, database_map: str
) -> None:
    """#2239 second review, Important finding (rows 2-4 of the 5-row matrix): before
    this fix, the handler checked `path_prefix is None` *inside* the `except
    D1StoreError`, so any D1StoreError raised while `path_prefix` happened to be `None`
    — invalid JSON, a non-object map, or the forbidden `""` key — was overwritten with
    the generic "path_prefix is required" message. An operator who saw that 400 and
    "fixed" it by adding a `""` key would retry and see the *identical* message, with
    no signal their edit was rejected. Config errors must surface as their own 503
    regardless of whether `path_prefix` was also omitted."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, database_map)

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes", arguments={"query": "jwt"}
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503
    assert "path_prefix is required" not in str(exc.value.detail)


def test_orchestrator_invoke_search_notes_d1_invalid_json_with_real_prefix_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Row 5 of the 5-row matrix, unaffected by the fix: a real `path_prefix` already
    took the 503 branch before this fix and must keep doing so."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, "{not json")

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={"query": "jwt", "path_prefix": "clients/digithings"},
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503
    assert "not valid JSON" in str(exc.value.detail)


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
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/digithings/nope", path_prefix="clients/digithings"
            ),
            _fake_request(),
        )
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
            ),
            _fake_request(),
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
        server.NoteByPathRequest(vault_path="clients/digithings", path_prefix="clients/digithings"),
        _fake_request(),
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
        ),
        _fake_request(),
    )
    assert result is note
    assert called["prefix"] == "clients/digithings"
    assert called["vault_path"] == "clients/digithings/arch"


def test_note_by_path_requires_path_prefix() -> None:
    """Minor #2239 second review finding: `path_prefix` is now a required field —
    `D1_DATABASE_MAP` may never carry a `""` entry (see `_load_d1_database_map`'s
    guard), so an omitted `path_prefix` could never resolve to a corpus and would
    only ever 503 at request time. Rejected up front at the schema boundary (422)
    instead of documenting a third "unscoped" state that no longer exists."""
    with pytest.raises(ValidationError):
        server.NoteByPathRequest(vault_path="clients/digithings/nope")


def test_get_note_by_path_returns_503_when_d1_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/digithings/x", path_prefix="clients/digithings"
            ),
            _fake_request(),
        )
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
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 400


def test_get_note_by_path_rejects_sibling_corpus_sharing_a_string_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review, Minor M5: the boundary check is
    `path != prefix and not path.startswith(prefix + "/")` — the `+ "/"` is load
    bearing. Weaken it to `not path.startswith(prefix)` (drop the separator) and
    `clients/digithings-archive/x` under prefix `clients/digithings` would pass,
    because the string "clients/digithings-archive/x" does start with the string
    "clients/digithings" even though the archive corpus is not a child of it. No
    existing test used two corpora that share a literal string prefix like this —
    every existing cross-corpus test used names with no common prefix at all
    (`clients/online-compliance-center` vs `clients/digithings`), so the classic
    string-prefix bug could be reintroduced without any test noticing."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for a sibling-corpus path")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/digithings-archive/x", path_prefix="clients/digithings"
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 403


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
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/digithings/x", path_prefix="clients/digithings"
            ),
            _fake_request(),
        )
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


# ── tenant-bound path_prefix (CodeRabbit review of promotion PR #2293) ──────────
# `digivault:read` alone lets any caller name any path_prefix — up to this point, the
# only boundary was "does vault_path fall under the *same request's* path_prefix",
# never "is this caller entitled to that path_prefix at all". These tests exercise
# the fix through the real `get_note_by_path`/`orchestrator_invoke` entry points
# (tests/dv/test_tenant_scope.py already covers `enforce_tenant_path_prefix` itself
# in isolation).
_TENANT_MAP = (
    '{"digithings": {"vaultPathPrefix": "clients/digithings"},'
    ' "occ": {"vaultPathPrefix": "clients/online-compliance-center"}}'
)


def test_get_note_by_path_refuses_a_prefix_outside_the_authenticated_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact gap CodeRabbit flagged: a digithings-tenant caller naming the occ
    corpus's own prefix (not merely escaping via vault_path — the prefix itself)."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store")

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/online-compliance-center/x",
                path_prefix="clients/online-compliance-center",
            ),
            _fake_request(tenant_slug="digithings"),
        )
    assert exc.value.status_code == 403
    assert "tenant" in str(exc.value.detail)


def test_get_note_by_path_allows_the_authenticated_tenants_own_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hi")

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            return note

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    result = server.get_note_by_path(
        server.NoteByPathRequest(
            vault_path="clients/digithings/arch", path_prefix="clients/digithings"
        ),
        _fake_request(tenant_slug="digithings"),
    )
    assert result is note


def test_orchestrator_invoke_get_note_refuses_a_prefix_outside_the_authenticated_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-session review of PR #2298: the by-path route and `digivault_search_notes`
    each had a dedicated cross-tenant test, but `digivault_get_note` — dispatched
    through `orchestrator_invoke`, a genuinely separate code path from the route even
    though both call the shared `_fetch_note_by_path` — did not. Both surfaces sharing
    a helper is exactly the kind of thing a future refactor could quietly break for
    only one of them; pin the tool-dispatch surface independently."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store")

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_get_note",
                arguments={
                    "vault_path": "clients/online-compliance-center/x",
                    "path_prefix": "clients/online-compliance-center",
                },
            ),
            _fake_request(tenant_slug="digithings"),
        )
    assert exc.value.status_code == 403


def test_orchestrator_invoke_get_note_allows_the_authenticated_tenants_own_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hi")

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            return note

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_path": "clients/digithings/arch",
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(tenant_slug="digithings"),
    )
    assert resp.ok is True


def test_get_note_by_path_refuses_an_unmapped_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once DIGI_TENANT_CORPUS_MAP is configured at all, a tenant slug absent from it
    has no authorized prefix — this must not fall back to "unscoped, allow"."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store")

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.get_note_by_path(
            server.NoteByPathRequest(
                vault_path="clients/digithings/arch", path_prefix="clients/digithings"
            ),
            _fake_request(tenant_slug="some-unrelated-tenant"),
        )
    assert exc.value.status_code == 403


def test_get_note_by_path_is_unaffected_when_tenant_map_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backward-compatibility guarantee: single-tenant deployments (this is the state
    of every other test in this file) never set DIGI_TENANT_CORPUS_MAP and must see
    no behavior change, even for a request whose tenant_slug doesn't match its own
    path_prefix in name (there is nothing to check it against)."""
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hi")

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            return note

    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    result = server.get_note_by_path(
        server.NoteByPathRequest(
            vault_path="clients/digithings/arch", path_prefix="clients/digithings"
        ),
        _fake_request(tenant_slug="totally-unrelated"),
    )
    assert result is note


def test_orchestrator_invoke_search_refuses_a_prefix_outside_the_authenticated_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same gap, exercised through `digivault_search_notes` rather than the by-path
    route/`digivault_get_note` — this is the tool digigraph proxies for every chat
    turn today (unlike `digivault_get_note`, not yet wired up in digigraph's
    builtin.py on `develop`), so it is the one actually reachable in production."""

    class _FakeD1:
        def search(self, query: str, *, limit: int, path_prefix: str | None) -> list:
            raise AssertionError("must not reach the store")

    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(
        monkeypatch, '{"clients/digithings": "db-1", "clients/online-compliance-center": "db-2"}'
    )
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={
                    "query": "policies",
                    "path_prefix": "clients/online-compliance-center",
                },
            ),
            _fake_request(tenant_slug="digithings"),
        )
    assert exc.value.status_code == 403


def test_orchestrator_invoke_search_allows_the_authenticated_tenants_own_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeD1:
        def search(self, query: str, *, limit: int, path_prefix: str | None) -> list:
            return []

    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(
        monkeypatch, '{"clients/digithings": "db-1", "clients/online-compliance-center": "db-2"}'
    )
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "policies", "path_prefix": "clients/digithings"},
        ),
        _fake_request(tenant_slug="digithings"),
    )
    assert resp.ok is True


def test_orchestrator_invoke_search_refuses_cross_tenant_prefix_on_local_vault_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CodeRabbit review of PR #2298: the first version of this fix only checked
    `path_prefix` on the D1 branch — the local-vault fallback (DIGIVAULT_ROOT set, no
    D1 credentials) read the same tenant-supplied prefix with no check at all. Tenant
    binding must apply uniformly across every backend, not just whichever one a given
    deployment happens to use."""
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    Vault(vault_root).create_note(
        "faq", subdir="clients/online-compliance-center", body="OCC help."
    )
    monkeypatch.setenv("DIGIVAULT_ROOT", str(vault_root))
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={
                    "query": "help",
                    "path_prefix": "clients/online-compliance-center",
                },
            ),
            _fake_request(tenant_slug="digithings"),
        )
    assert exc.value.status_code == 403


def test_orchestrator_invoke_search_refuses_cross_tenant_prefix_on_supabase_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same gap, third backend: no DIGIVAULT_ROOT and no D1 credentials falls through
    to Supabase FTS, which must be equally bound to the caller's tenant."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)

    def _boom() -> SupabaseStore:
        raise AssertionError("must not reach Supabase for a refused cross-tenant prefix")

    monkeypatch.setattr(server.SupabaseStore, "from_env", _boom)

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={
                    "query": "help",
                    "path_prefix": "clients/online-compliance-center",
                },
            ),
            _fake_request(tenant_slug="digithings"),
        )
    assert exc.value.status_code == 403


def test_by_path_route_end_to_end_refuses_cross_tenant_prefix_via_real_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full stack, not fakes: a real signed JWT (tenant_slug="digithings", minted by
    tests/digi_test_jwt.py exactly as production's DigiAuthMiddleware would verify
    it) hitting the real HTTP route via TestClient, requesting the occ corpus's own
    prefix. Proves the DigiAuthMiddleware -> request.state.digi_auth -> _tenant_slug
    -> enforce_tenant_path_prefix wiring end to end, not just the unit-level pieces."""

    class _RefusingD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for the mismatched prefix")

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _TENANT_MAP)
    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _RefusingD1())
    client = TestClient(server.app)

    resp = client.post(
        "/v1/notes/by-path",
        json={
            "vault_path": "clients/online-compliance-center/x",
            "path_prefix": "clients/online-compliance-center",
        },
        headers=auth_headers(scopes=[SCOPE_READ], tenant_slug="digithings"),
    )
    assert resp.status_code == 403

    note = NoteDetail(vault_path="clients/digithings/x", title="x", body_markdown="hi")
    monkeypatch.setattr(
        server, "_open_d1_store", lambda prefix: SimpleNamespace(get_note=lambda p: note)
    )
    ok = client.post(
        "/v1/notes/by-path",
        json={"vault_path": "clients/digithings/x", "path_prefix": "clients/digithings"},
        headers=auth_headers(scopes=[SCOPE_READ], tenant_slug="digithings"),
    )
    assert ok.status_code == 200


# ── digivault_get_note orchestrator tool (#2239 Task 3 gap) ─────────────────────
def test_orchestrator_invoke_get_note_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full round trip through the shared `_fetch_note_by_path` helper — the note
    body must come back in `data`, not just a bare ok flag."""
    note = NoteDetail(
        vault_path="clients/digithings/arch", title="Arch", body_markdown="hello world"
    )
    called: dict = {}

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail | None:
            called["vault_path"] = vault_path
            return note

    def _open(prefix: str | None) -> _FakeD1:
        called["prefix"] = prefix
        return _FakeD1()

    monkeypatch.setattr(server, "_open_d1_store", _open)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_path": "clients/digithings/arch",
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data["vault_path"] == "clients/digithings/arch"
    assert resp.data["body_markdown"] == "hello world"
    assert called["prefix"] == "clients/digithings"
    assert called["vault_path"] == "clients/digithings/arch"


def test_orchestrator_invoke_get_note_missing_vault_path_is_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing/blank vault_path is an argument-level error: ok=False, not a raised
    HTTP error — the same convention digivault_search_notes uses for `query`, so the
    reason survives digigraph's `raise_for_status()` hop (`str(httpx.HTTPStatusError)`
    drops the body — see the search_notes tests above)."""

    def _boom(prefix: str | None) -> None:
        raise AssertionError("must not open a store when vault_path is missing")

    monkeypatch.setattr(server, "_open_d1_store", _boom)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note", arguments={"path_prefix": "clients/digithings"}
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "vault_path is required"

    resp_blank = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={"vault_path": "   ", "path_prefix": "clients/digithings"},
        ),
        _fake_request(),
    )
    assert resp_blank.ok is False
    assert resp_blank.error == "vault_path is required"


def test_orchestrator_invoke_get_note_missing_path_prefix_is_ok_false_not_unscoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The production gap this dispatch branch must not paper over: even now that
    digigraph's `_handle_digivault_get_note` injects the caller's tenant context
    (mirroring `_handle_digivault_search`'s `digivault_search_notes` handling,
    #2240), a session with no mapped tenant corpus still gets `path_prefix=None`
    passed through unconditionally — digigraph has no unscoped default to fall
    back to. Defaulting to an unscoped read here (resolve_path_prefix(None) means
    "no scoping requested") would be exactly the cross-tenant fail-open the by-path
    route's required path_prefix field exists to prevent. Must refuse instead."""

    def _boom(prefix: str | None) -> None:
        raise AssertionError("must not open a store — path_prefix is absent")

    monkeypatch.setattr(server, "_open_d1_store", _boom)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note", arguments={"vault_path": "clients/digithings/arch"}
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "path_prefix is required for digivault_get_note"


@pytest.mark.parametrize("blank_prefix", ["", "/", "///", "   ", ".md"])
def test_orchestrator_invoke_get_note_blank_path_prefix_is_ok_false_not_a_raised_400(
    monkeypatch: pytest.MonkeyPatch, blank_prefix: str
) -> None:
    """#2239 review, Minor M1: `path_prefix_arg is None` was the only condition that
    produced the readable `ok=False` refusal; a *present but blank* value ("", "/",
    "   ", ".md") survived that check and fell through to `_fetch_note_by_path`,
    whose `resolve_path_prefix` raises `ValueError` for exactly this case (wrapped as
    `HTTPException(400)`) — reaching a real digigraph caller only as a bare
    "Client error '400 Bad Request'" once `raise_for_status()` drops the body.
    `vault_path` two lines above already treats blank the same as absent; `path_prefix`
    must match that convention and produce the same message as the omitted case."""

    def _boom(prefix: str | None) -> None:
        raise AssertionError("must not open a store — path_prefix is blank, not scoped")

    monkeypatch.setattr(server, "_open_d1_store", _boom)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={"vault_path": "clients/digithings/arch", "path_prefix": blank_prefix},
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "path_prefix is required for digivault_get_note"


def test_orchestrator_invoke_get_note_refuses_cross_corpus_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller scoped to `clients/digithings` must not read the OCC corpus by
    passing an arbitrary vault_path through the orchestrator tool — same 403 the
    `POST /v1/notes/by-path` route raises for the identical inputs, because both
    go through the same `_fetch_note_by_path` helper."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for an out-of-scope path")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_get_note",
                arguments={
                    "vault_path": "clients/online-compliance-center/x",
                    "path_prefix": "clients/digithings",
                },
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 403

    # Prove the refusal is the authorization check, not an accident of the fake: with
    # the check removed (a store that would happily answer for any prefix), the same
    # cross-corpus call must succeed — pinning that the 403 above depends on
    # `_fetch_note_by_path`'s prefix enforcement actually running.
    note = NoteDetail(vault_path="clients/online-compliance-center/x", title="x", body_markdown="")
    monkeypatch.setattr(server, "_fetch_note_by_path", lambda vault_path, path_prefix, **_kw: note)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_path": "clients/online-compliance-center/x",
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True


def test_orchestrator_invoke_get_note_refuses_sibling_corpus_sharing_a_string_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review, Minor M5 (tool-branch surface): same string-prefix regression as
    `test_get_note_by_path_rejects_sibling_corpus_sharing_a_string_prefix`, exercised
    through `orchestrator_invoke` rather than the route directly — both surfaces must
    catch `clients/digithings-archive/x` escaping a `clients/digithings` scope, not
    just the route (they currently share `_fetch_note_by_path`, but this pins the
    public tool-call contract independently of that implementation detail)."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for a sibling-corpus path")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_get_note",
                arguments={
                    "vault_path": "clients/digithings-archive/x",
                    "path_prefix": "clients/digithings",
                },
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 403


def test_orchestrator_invoke_get_note_not_found_is_clean_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale or mistyped vault_path must read as a recoverable 'not found', not an
    exception — the model should be able to retry with a different path."""

    class _FakeD1:
        def get_note(self, vault_path: str) -> None:
            return None

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_path": "clients/digithings/nope",
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "note not found: clients/digithings/nope"


def test_orchestrator_invoke_get_note_d1_unconfigured_returns_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    monkeypatch.delenv("D1_DATABASE_MAP", raising=False)
    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_get_note",
                arguments={
                    "vault_path": "clients/digithings/arch",
                    "path_prefix": "clients/digithings",
                },
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 503


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
        json={"vault_path": "clients/digithings/arch", "path_prefix": "clients/digithings"},
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


# ── digivault_get_note batch (vault_paths) — #2306 follow-up ────────────────────
def test_orchestrator_invoke_get_note_batch_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """vault_paths fetches several notes in one call, response shape is {"notes": [...],
    "errors": {}} — distinct from the single-path shape, which stays a bare note dict."""
    notes_by_path = {
        "clients/digithings/arch__p001": NoteDetail(
            vault_path="clients/digithings/arch__p001", title="Arch p1", body_markdown="page one"
        ),
        "clients/digithings/arch__p002": NoteDetail(
            vault_path="clients/digithings/arch__p002", title="Arch p2", body_markdown="page two"
        ),
    }

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail | None:
            return notes_by_path.get(vault_path)

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_paths": [
                    "clients/digithings/arch__p001",
                    "clients/digithings/arch__p002",
                ],
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data["errors"] == {}
    got = {n["vault_path"]: n["body_markdown"] for n in resp.data["notes"]}
    assert got == {
        "clients/digithings/arch__p001": "page one",
        "clients/digithings/arch__p002": "page two",
    }


def test_orchestrator_invoke_get_note_batch_partial_failure_keeps_the_good_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad path in a batch of six must not discard the other five — the model gets
    what succeeded plus a keyed error for what didn't, and can still answer."""
    good = NoteDetail(
        vault_path="clients/digithings/arch__p001", title="Arch p1", body_markdown="ok"
    )

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail | None:
            return good if vault_path == "clients/digithings/arch__p001" else None

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_paths": ["clients/digithings/arch__p001", "clients/digithings/arch__p999"],
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert len(resp.data["notes"]) == 1
    assert resp.data["notes"][0]["vault_path"] == "clients/digithings/arch__p001"
    assert resp.data["errors"] == {
        "clients/digithings/arch__p999": "note not found: clients/digithings/arch__p999"
    }


def test_orchestrator_invoke_get_note_batch_enforces_prefix_per_path_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The #2265/#2239/#2298 tenant-scope check must run for EVERY path in a batch, not
    just get short-circuited after the first one passes — a batch must not become a way
    to smuggle one cross-corpus path past the boundary the single-path case enforces."""
    in_scope = NoteDetail(
        vault_path="clients/digithings/arch__p001", title="P1", body_markdown="ok"
    )

    class _FakeD1:
        def get_note(self, vault_path: str) -> NoteDetail:
            raise AssertionError("must not reach the store for the out-of-scope path")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    monkeypatch.setattr(
        server,
        "_fetch_note_by_path",
        lambda vault_path, path_prefix, **_kw: (
            in_scope
            if vault_path == "clients/digithings/arch__p001"
            else (_ for _ in ()).throw(HTTPException(status_code=403, detail="out of scope"))
        ),
    )
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_paths": [
                    "clients/digithings/arch__p001",
                    "clients/online-compliance-center/x",
                ],
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert len(resp.data["notes"]) == 1
    assert resp.data["notes"][0]["vault_path"] == "clients/digithings/arch__p001"
    assert resp.data["errors"] == {"clients/online-compliance-center/x": "out of scope"}


def test_orchestrator_invoke_get_note_batch_dedupes_while_preserving_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    note = NoteDetail(vault_path="clients/digithings/arch__p001", title="P1", body_markdown="ok")

    class _FakeD1:
        calls: list[str] = []

        def get_note(self, vault_path: str) -> NoteDetail | None:
            _FakeD1.calls.append(vault_path)
            return note

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_paths": [
                    "clients/digithings/arch__p001",
                    "clients/digithings/arch__p001",
                ],
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert len(resp.data["notes"]) == 1
    assert _FakeD1.calls == ["clients/digithings/arch__p001"]


def test_orchestrator_invoke_get_note_batch_empty_list_is_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(prefix: str | None) -> None:
        raise AssertionError("must not open a store for an empty vault_paths")

    monkeypatch.setattr(server, "_open_d1_store", _boom)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={"vault_paths": ["   ", ""], "path_prefix": "clients/digithings"},
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.error == "vault_paths must contain at least one path"


def test_orchestrator_invoke_get_note_single_path_unchanged_when_vault_paths_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression pin: adding vault_paths must not alter the singular vault_path
    response shape at all — a direct API caller who has never heard of vault_paths
    must see byte-identical behaviour after this change."""
    note = NoteDetail(vault_path="clients/digithings/arch", title="Arch", body_markdown="hello")
    monkeypatch.setattr(
        server, "_open_d1_store", lambda prefix: SimpleNamespace(get_note=lambda p: note)
    )
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={
                "vault_path": "clients/digithings/arch",
                "path_prefix": "clients/digithings",
            },
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data is not None
    assert resp.data == note.model_dump(mode="json")
    assert "notes" not in resp.data
    assert "errors" not in resp.data


@pytest.mark.unit
@pytest.mark.parametrize("empty_prefix", ["", "/", "   ", "///", ".md"])
def test_orchestrator_invoke_search_notes_rejects_empty_normalizing_prefix_at_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, empty_prefix: str
) -> None:
    """#2407/#2408: present-but-empty prefix is refused at the endpoint (ok=False)."""
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "secret",
        subdir="clients/acme",
        frontmatter={"title": "Acme confidential plan"},
        body="Acme confidential merger acquisition roadmap secret plan.",
    )
    monkeypatch.setenv("DIGIVAULT_ROOT", str(root))
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "Acme confidential merger", "path_prefix": empty_prefix},
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert "normalizes to empty" in (resp.error or "")


@pytest.mark.unit
def test_orchestrator_invoke_search_notes_rejects_md_md_prefix_via_local_vault(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`.md.md` survives one normalize pass (→ `.md`); local search rejects on the second."""
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("DIGIVAULT_ROOT", str(root))
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)

    with pytest.raises(HTTPException) as exc:
        server.orchestrator_invoke(
            server.OrchestratorInvokeRequest(
                tool="digivault_search_notes",
                arguments={"query": "Acme confidential merger", "path_prefix": ".md.md"},
            ),
            _fake_request(),
        )
    assert exc.value.status_code == 400
    assert "empty" in str(exc.value.detail)


@pytest.mark.unit
@pytest.mark.parametrize("empty_prefix", ["", "/", "   ", "///", ".md"])
def test_orchestrator_invoke_search_notes_rejects_empty_normalizing_prefix_ok_false_for_d1(
    monkeypatch: pytest.MonkeyPatch, empty_prefix: str
) -> None:
    """#2408: empty-normalizing prefix returns ok=False on D1, matching digivault_get_note."""
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch, '{"clients/digithings": "db-1"}')
    monkeypatch.setattr(
        server,
        "_open_d1_store",
        lambda prefix: (_ for _ in ()).throw(AssertionError("must not open store")),
    )

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "jwt", "path_prefix": empty_prefix},
        ),
        _fake_request(),
    )
    assert resp.ok is False
    assert resp.tool == "digivault_search_notes"
    assert "normalizes to empty" in (resp.error or "")


@pytest.mark.unit
def test_orchestrator_invoke_search_notes_omitted_prefix_still_searches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Omitting path_prefix remains the deliberate opt-out from scoping."""
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "secret",
        subdir="clients/acme",
        frontmatter={"title": "Acme confidential plan"},
        body="Acme confidential merger acquisition roadmap secret plan.",
    )
    monkeypatch.setenv("DIGIVAULT_ROOT", str(root))
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)

    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            arguments={"query": "Acme confidential merger"},
        ),
        _fake_request(),
    )
    assert resp.ok is True
    assert resp.data["hits"]
