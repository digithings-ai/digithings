"""Acceptance test 5 (DIG-912 §5.4, reviewer correction A2) — BOTH digivault seams.

digivault runs TWO separate ASGI applications: the FastAPI app in `server.py`,
and a distinct `FastMCP("digivault")` in `mcp_server.py:23` listening on
streamable HTTP at 127.0.0.1:8769 with **no `add_middleware` at all**. These are
two applications, not two code paths through one, so the Art. 9 screen has to
exist in both:

* the HTTP seam, inside `_write_note_request` (`server.py:628`) — the single
  funnel serving `POST /v1/notes` and `POST /v1/notes/batch`;
* the MCP seam, inside `dispatch_vault_tool` (`tool_dispatch.py:252`), BEFORE
  the handler dispatch.

Revision 1 of the spec said "both required" without the reason, and a
well-meaning simplification then left MCP unprotected with every test green.
That is what this module makes checkable: tests 4 and 5 drive the second
application with no HTTP app in the path, so a screen that only exists in
`server.py` fails here.

Every refusal test asserts the markdown file is ABSENT from disk, and the
positive-control tests write a clean note through both seams, so a screen that
refuses everything cannot pass vacuously.

Provenance: spec §5.4 + acceptance test 5 on DIG-912; reviewer correction A2 on
DIG-912; plan L8 on DIG-959; leaf DIG-1081.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("digikey")
pytest.importorskip("digibase")
pytest.importorskip("mcp.server.fastmcp")

from digivault.path_scopes import SCOPE_WRITE
from digivault.tool_dispatch import TOOL_VAULT_CREATE_NOTE, dispatch_vault_tool
from digivault.vault import Vault
from fastapi.testclient import TestClient

from digivault import mcp_server, server, tool_dispatch
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

# An NHS number is one of the eight Art. 9(1) categories L1 detects as an
# identifier pattern; the prose around it is deliberately ordinary so the test
# pins the identifier signal and not a sentence.
ART9_BODY = "Patient record. NHS number 943 476 5919. See also the letter."
CLEAN_BODY = "Deployment notes. Nothing special in this body."
ART9_REASON = "art9:health:nhs_number"
REFUSAL_MARKER = "art9"


def _vault_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty vault root. Empty on purpose: `glob("*.md") == []` then means
    'this leaf wrote nothing', with no seeded notes to subtract."""
    monkeypatch.setenv("DIGIVAULT_ROOT", str(tmp_path))
    return tmp_path


def _fake_request(scopes: list[str] | None = None) -> SimpleNamespace:
    """Stand-in for FastAPI's Request — only `_require_tool_scope` reads it."""
    return SimpleNamespace(
        state=SimpleNamespace(
            digi_auth=SimpleNamespace(scopes=scopes or [], tenant_slug="digithings")
        )
    )


def _notes_on_disk(root: Path) -> list[str]:
    return sorted(p.name for p in root.glob("*.md"))


def _detail(resp: object) -> str:
    """digivault installs digibase's standard error envelope, so a raised
    HTTPException.detail lands at error.message, not at a top-level `detail`."""
    return str(resp.json()["error"]["message"])  # type: ignore[attr-defined]


def _auth() -> dict[str, str]:
    return auth_headers(scopes=[SCOPE_WRITE], tenant_slug="digithings")


# ── seam 1: the HTTP application (server.py) ─────────────────────────────────


def test_post_v1_notes_refuses_art9_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 1 — refusal on POST /v1/notes, markdown file not written."""
    root = _vault_root(tmp_path, monkeypatch)
    resp = TestClient(server.app).post(
        "/v1/notes",
        json={"name": "patient", "body": ART9_BODY},
        headers=_auth(),
    )
    assert resp.status_code == 403, resp.text
    assert ART9_REASON in _detail(resp)
    assert _notes_on_disk(root) == []


def test_post_v1_notes_batch_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 2 — refusal on POST /v1/notes/batch, markdown files not written."""
    root = _vault_root(tmp_path, monkeypatch)
    resp = TestClient(server.app).post(
        "/v1/notes/batch",
        json={
            "notes": [{"name": "patient", "body": ART9_BODY}, {"name": "clean", "body": CLEAN_BODY}]
        },
        headers=_auth(),
    )
    assert resp.status_code == 403, resp.text
    assert ART9_REASON in _detail(resp)
    assert _notes_on_disk(root) == []


def test_batch_refusal_is_per_note_and_not_a_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A batch is screened note by note, before each write — not transactionally.

    A clean note listed before the offending one is already on disk when the
    refusal fires. Pinned so the refusal is never read as a batch rollback, and
    so the offending note's own file is proven unwritten.
    """
    root = _vault_root(tmp_path, monkeypatch)
    resp = TestClient(server.app).post(
        "/v1/notes/batch",
        json={
            "notes": [{"name": "clean", "body": CLEAN_BODY}, {"name": "patient", "body": ART9_BODY}]
        },
        headers=_auth(),
    )
    assert resp.status_code == 403, resp.text
    assert _notes_on_disk(root) == ["clean.md"]
    assert not (root / "patient.md").exists()


# ── seam 2: the MCP application (mcp_server.py) ──────────────────────────────


def _mcp_call(tool: str, arguments: dict[str, object]) -> str:
    """Call a tool as the MCP application really does — through the registered
    FastMCP tool manager, with no HTTP app in the path."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("digivault-art9-test", json_response=True)
    tool_dispatch.register_mcp_tools(mcp, mcp_server._open_vault)
    result = asyncio.run(mcp._tool_manager.call_tool(tool, arguments))
    return str(result[0]) if isinstance(result, tuple) else str(result)


def test_mcp_application_write_tool_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 3 — refusal through dispatch_vault_tool ON THE MCP APPLICATION."""
    root = _vault_root(tmp_path, monkeypatch)
    monkeypatch.setenv("DIGIVAULT_MCP_WRITE", "1")
    out = _mcp_call("create_note", {"name": "patient", "body": ART9_BODY})
    assert REFUSAL_MARKER in out, out
    assert ART9_REASON in out, out
    assert _notes_on_disk(root) == []


def test_mcp_path_reached_through_orchestrator_invoke_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acceptance 4 — the same refusal via server.py's dispatch_vault_tool call,
    the second entry point into the second application."""
    root = _vault_root(tmp_path, monkeypatch)
    resp = server.orchestrator_invoke(
        server.OrchestratorInvokeRequest(
            tool="digivault_create_note",
            arguments={"name": "patient", "body": ART9_BODY},
        ),
        _fake_request(scopes=[SCOPE_WRITE]),
    )
    assert resp.ok is False
    assert resp.error is not None
    assert REFUSAL_MARKER in resp.error, resp.error
    assert ART9_REASON in resp.error, resp.error
    assert _notes_on_disk(root) == []


def test_dispatch_vault_tool_is_the_mcp_seam_and_still_dispatches_clean_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screened seam is `dispatch_vault_tool` itself, and it is not a
    refuse-everything stub: the same call writes a clean note."""
    root = _vault_root(tmp_path, monkeypatch)
    vault = Vault(root)

    refused = dispatch_vault_tool(
        TOOL_VAULT_CREATE_NOTE, {"name": "patient", "body": ART9_BODY}, vault
    )
    assert refused.ok is False
    assert refused.error is not None and ART9_REASON in refused.error
    assert _notes_on_disk(root) == []

    allowed = dispatch_vault_tool(
        TOOL_VAULT_CREATE_NOTE, {"name": "clean", "body": CLEAN_BODY}, vault
    )
    assert allowed.ok is True, allowed.error
    assert _notes_on_disk(root) == ["clean.md"]


# ── the two-applications reason, made checkable ──────────────────────────────


def test_every_mcp_write_passes_through_the_screened_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MCP application owns no handler of its own, so its writes can only
    reach the vault through the screened seam.

    Proved by spy rather than by grepping the module: `mcp_server.py` NAMES
    `VAULT_HANDLERS` and `@mcp.tool` in its own docstring and comments (to
    forbid them), so a source scan reads that prose as a violation. What
    matters is the call, not the word.
    """
    root = _vault_root(tmp_path, monkeypatch)
    monkeypatch.setenv("DIGIVAULT_MCP_WRITE", "1")
    seen: list[str] = []
    real_dispatch = tool_dispatch.dispatch_vault_tool

    def spy(name: str, args: object, vault: object) -> object:
        seen.append(name)
        return real_dispatch(name, args, vault)

    monkeypatch.setattr(tool_dispatch, "dispatch_vault_tool", spy)
    out = _mcp_call("create_note", {"name": "clean", "body": CLEAN_BODY})
    assert TOOL_VAULT_CREATE_NOTE in seen, out
    assert _notes_on_disk(root) == ["clean.md"]

    # The contrast that makes the reason checkable: the first application does
    # mount middleware; the second one has no admission middleware of its own,
    # which is exactly why the screen has to live in the dispatch seam.
    assert "add_middleware" in inspect.getsource(server)


def test_clean_note_is_written_over_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive control for the HTTP seam — without it, 403 everywhere would pass."""
    root = _vault_root(tmp_path, monkeypatch)
    resp = TestClient(server.app).post(
        "/v1/notes",
        json={"name": "clean", "body": CLEAN_BODY},
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    assert _notes_on_disk(root) == ["clean.md"]


def test_refusal_never_echoes_the_matched_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is a refusal, not a copy of the identifier it caught."""
    _vault_root(tmp_path, monkeypatch)
    resp = TestClient(server.app).post(
        "/v1/notes",
        json={"name": "patient", "body": ART9_BODY},
        headers=_auth(),
    )
    assert "943 476 5919" not in resp.text
