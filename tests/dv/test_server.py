"""Service-layer tests. Skipped unless the [service] extra (fastapi/digikey) is installed."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from digivault import server  # noqa: E402
from digivault.orchestrator_tools import ORCHESTRATOR_TOOL_NAMES  # noqa: E402
from digivault.path_scopes import SCOPE_WRITE  # noqa: E402
from digivault.supabase_store import SupabaseStore  # noqa: E402

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
    # No DigiKey configured -> middleware returns 503 auth_not_configured.
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
        "title": "DigiGraph",
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
            "title": "DigiGraph",
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
            {"query": "what does digigraph orchestrate", "match_limit": 3},
        )
    ]


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
        ("search_architecture_notes", {"query": "auth", "match_limit": 7})
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
        ("search_architecture_notes", {"query": "auth", "match_limit": 50})
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
        ("search_architecture_notes", {"query": "auth", "match_limit": 1})
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
