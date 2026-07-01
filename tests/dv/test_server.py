"""Service-layer tests. Skipped unless the [service] extra (fastapi/digikey) is installed."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")

from fastapi.testclient import TestClient  # noqa: E402

from digivault import server  # noqa: E402
from digivault.orchestrator_tools import ORCHESTRATOR_TOOL_NAMES  # noqa: E402

pytestmark = pytest.mark.unit


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
