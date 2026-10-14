"""Commercial-license guard for LuxAlgo indicator source code (#4845).

Self-enforcing CC BY-NC-SA boundary: no ``library_get_source_code`` payload
may be persisted (Chroma / Supabase / documents rows) or rendered into paid
digiquant surfaces (tearsheets, briefs, chat answers) unless the commercial
Library license flag (``LUXALGO_COMMERCIAL_LICENSE``, default OFF) is on.

Layers pinned here: flag parsing, live-surface exposure (MCP full/read,
read scope, manifest, entitlements, schemas, research subset, dispatcher),
dispatcher runtime refusal, payload-shape detection, per-state attribution,
and the repo-wide code scan backstop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("mcp.server.fastmcp")

pytestmark = pytest.mark.unit

from digiquant.data.luxalgo import (  # noqa: E402
    LUXALGO_COMMERCIAL_LICENSE_ENV,
    LUXALGO_DISPATCH,
    LUXALGO_ENABLED_ENV,
    LUXALGO_LICENSE_STATE_NOTE_DISABLED,
    LUXALGO_LICENSE_STATE_NOTE_ENABLED,
    LUXALGO_TOOLS,
    RESEARCH_TOOLS,
    SOURCE_CODE_TOOL_NAME,
    TOOL_ENTITLEMENTS,
    LicenseBoundaryError,
    LuxAlgoClient,
    assert_payload_has_no_source_code,
    attribution_fields,
    build_luxalgo_tool_dispatcher,
    commercial_license_note,
    is_source_code_tool,
    luxalgo_commercial_license_enabled,
    payload_contains_source_code,
    run_boundary_checks,
    scan_source_code_references,
    source_code_violations,
)
from digiquant.mcp_server import READ_SCOPE_TOOLS, create_mcp_server  # noqa: E402
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LUXALGO_ENABLED_ENV, raising=False)
    monkeypatch.delenv(LUXALGO_COMMERCIAL_LICENSE_ENV, raising=False)


def _live_surfaces() -> dict[str, set[str]]:
    full = {tool.name for tool in create_mcp_server(scope="full")._tool_manager.list_tools()}
    read = {tool.name for tool in create_mcp_server(scope="read")._tool_manager.list_tools()}
    manifest = {tool["function"]["name"] for tool in build_orchestrator_tool_manifest()}
    return {
        "mcp_full": full,
        "mcp_read": read,
        "read_scope": set(READ_SCOPE_TOOLS),
        "manifest": manifest,
        "entitlements": set(TOOL_ENTITLEMENTS),
        "agent_schemas": {tool["function"]["name"] for tool in LUXALGO_TOOLS},
        "research_subset": set(RESEARCH_TOOLS),
        "dispatcher": set(LUXALGO_DISPATCH),
    }


def _fail_handler(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request expected, got {request.url}")


# ── flag parsing (default OFF) ──────────────────────────────────────────


def test_commercial_flag_defaults_off() -> None:
    assert luxalgo_commercial_license_enabled() is False


def test_commercial_flag_truthy_enables() -> None:
    for raw in ("1", "true", "TRUE", "yes", "On", "  on  "):
        assert luxalgo_commercial_license_enabled(raw=raw) is True


def test_commercial_flag_falsy_or_typo_stays_off() -> None:
    for raw in ("", "   ", "0", "false", "off", "no", "typo", "licenced"):
        assert luxalgo_commercial_license_enabled(raw=raw) is False


def test_commercial_flag_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LUXALGO_COMMERCIAL_LICENSE_ENV, "1")
    assert luxalgo_commercial_license_enabled() is True
    monkeypatch.setenv(LUXALGO_COMMERCIAL_LICENSE_ENV, "0")
    assert luxalgo_commercial_license_enabled() is False


# ── exposure: live surfaces carry no source-code tool ───────────────────


def test_no_surface_exposes_source_code_without_license() -> None:
    assert source_code_violations(_live_surfaces(), commercial=False) == []


def test_no_surface_exposes_source_code_with_license_either() -> None:
    # Nothing is wired yet: even licensed, every live surface is clean.
    assert source_code_violations(_live_surfaces(), commercial=True) == []


def test_guard_respects_flag_for_dispatcher_only() -> None:
    licensed_dispatcher = {**_live_surfaces(), "dispatcher": set(LUXALGO_DISPATCH)}
    licensed_dispatcher["dispatcher"].add(SOURCE_CODE_TOOL_NAME)
    assert source_code_violations(licensed_dispatcher, commercial=False) != []
    # When ON the 9th tool may be added to the dispatcher.
    assert source_code_violations(licensed_dispatcher, commercial=True) == []


def test_always_free_surfaces_stay_closed_when_licensed() -> None:
    for surface in ("mcp_full", "mcp_read", "read_scope", "manifest", "entitlements"):
        surfaces = {**_live_surfaces(), surface: set(_live_surfaces()[surface])}
        surfaces[surface].add(SOURCE_CODE_TOOL_NAME)
        assert source_code_violations(surfaces, commercial=True) != []


def test_is_source_code_tool_covers_both_spellings() -> None:
    assert is_source_code_tool(SOURCE_CODE_TOOL_NAME) is True
    assert is_source_code_tool("luxalgo_library_search") is False


# ── dispatcher runtime refusal (no request without the license) ─────────


def test_dispatcher_refuses_source_code_without_license() -> None:
    client = LuxAlgoClient(transport=httpx.MockTransport(_fail_handler))
    result = build_luxalgo_tool_dispatcher(client)(SOURCE_CODE_TOOL_NAME, {"slug": "rsi"})
    assert result["ok"] is False
    payload = json.loads(result["content"])
    assert payload["data"]["code"] == "invalid_input"
    assert payload["data"]["retryable"] is False
    assert "commercial" in payload["data"]["message"].lower()


def test_dispatcher_falls_through_to_unknown_when_licensed_but_unwired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Licensed but no dispatch row exists (procurement is owner-side): the
    # name is unknown, not refused — wiring it is a deliberate future change.
    monkeypatch.setenv(LUXALGO_COMMERCIAL_LICENSE_ENV, "1")
    client = LuxAlgoClient(transport=httpx.MockTransport(_fail_handler))
    result = build_luxalgo_tool_dispatcher(client)(SOURCE_CODE_TOOL_NAME, {"slug": "rsi"})
    assert result["ok"] is False
    assert "unknown luxalgo tool" in result["content"]


# ── payload-shape detection ─────────────────────────────────────────────


def test_payload_shape_detection() -> None:
    assert payload_contains_source_code({"source_code": "//@version=5"}) is True
    assert payload_contains_source_code({"data": {"PINE_SCRIPT": "study()"}}) is True
    assert payload_contains_source_code([{"script_source": "x"}]) is True
    assert payload_contains_source_code({"source_code": "   "}) is False
    assert payload_contains_source_code({"source_code": None}) is False
    assert payload_contains_source_code({"slug": "rsi", "limit": 2}) is False
    assert payload_contains_source_code("source_code") is False
    assert payload_contains_source_code(None) is False


def test_assert_payload_refuses_source_shaped_payload() -> None:
    with pytest.raises(LicenseBoundaryError):
        assert_payload_has_no_source_code({"pine_source": "study()"}, surface="supabase")
    # Metadata payloads pass through silently.
    assert_payload_has_no_source_code({"slug": "rsi"}, surface="tearsheets")


# ── attribution covers both flag states ─────────────────────────────────


def test_license_note_covers_both_states() -> None:
    assert commercial_license_note(True) == LUXALGO_LICENSE_STATE_NOTE_ENABLED
    assert commercial_license_note(False) == LUXALGO_LICENSE_STATE_NOTE_DISABLED
    assert "not enabled (default)" in commercial_license_note(False)


def test_attribution_block_states_unlicensed_by_default() -> None:
    fields = attribution_fields()
    assert fields["commercial_license"] is False
    assert fields["license_state"] == LUXALGO_LICENSE_STATE_NOTE_DISABLED
    assert fields["attribution"] == "Sourced from LuxAlgo Library"


def test_attribution_block_states_licensed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LUXALGO_COMMERCIAL_LICENSE_ENV, "yes")
    fields = attribution_fields("https://luxalgo.com/library/rsi/")
    assert fields["commercial_license"] is True
    assert fields["license_state"] == LUXALGO_LICENSE_STATE_NOTE_ENABLED
    assert fields["source_url"] == "https://luxalgo.com/library/rsi/"
    # Explicit pin overrides the live flag.
    assert attribution_fields(commercial_license=False)["commercial_license"] is False


def test_licensed_payload_serializes_to_json() -> None:
    assert (
        json.loads(json.dumps(attribution_fields(commercial_license=True)))["commercial_license"]
        is True
    )


# ── repo scan backstop ──────────────────────────────────────────────────


def test_repo_scan_is_clean() -> None:
    assert (REPO_ROOT / "digiquant").is_dir()
    assert scan_source_code_references(REPO_ROOT) == []


def test_repo_scan_detects_planted_reference(tmp_path: Path) -> None:
    planted = tmp_path / "evil_sink.py"
    planted.write_text(
        'def persist(payload):\n    return call("library_get_source_code", payload)\n',
        encoding="utf-8",
    )
    (tmp_path / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert scan_source_code_references(tmp_path) == ["evil_sink.py:2"]


def test_full_boundary_check_is_clean() -> None:
    assert run_boundary_checks(REPO_ROOT, _live_surfaces(), commercial=False) == []


def test_full_boundary_check_reports_exposure(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("VALUE = 1\n", encoding="utf-8")
    surfaces: dict[str, Any] = {**_live_surfaces(), "manifest": {SOURCE_CODE_TOOL_NAME}}
    violations = run_boundary_checks(tmp_path, surfaces, commercial=False)
    assert any("manifest" in violation for violation in violations)
