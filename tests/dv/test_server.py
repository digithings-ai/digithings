"""Service-layer tests. Skipped unless the [service] extra (fastapi/digikey) is installed."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from digivault import server  # noqa: E402
from digivault.orchestrator_tools import ORCHESTRATOR_TOOL_NAMES  # noqa: E402
from digivault.supabase_store import SupabaseStore  # noqa: E402

pytestmark = pytest.mark.unit


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
        server.OrchestratorInvokeRequest(tool="digivault_search_tag", arguments={"tag": "doc"})
    )
    assert resp.ok is True
    assert resp.data is not None
    assert [n["name"] for n in resp.data["notes"]] == ["a"]


def test_orchestrator_invoke_unknown_tool(vault_dir: Path) -> None:
    with pytest.raises(Exception):
        server.orchestrator_invoke(server.OrchestratorInvokeRequest(tool="nope"))


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
        )
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
        )
    )
    assert fake_client.rpc_calls == [
        ("search_architecture_notes", {"query": "auth", "match_limit": 7})
    ]


def test_orchestrator_invoke_search_notes_missing_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(tool="digivault_search_notes", arguments={"query": "   "})
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
            )
        )
    assert excinfo.value.status_code == 503
