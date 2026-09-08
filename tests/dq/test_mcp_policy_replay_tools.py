"""WP16.9 — MCP discovery and side-effect boundaries for policy replay (#3011)."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

pytestmark = pytest.mark.unit

_REQUIRED = {
    "dashboard_run_policy_replay",
    "dashboard_get_policy_replay",
    "dashboard_get_policy_comparison",
    "dashboard_evaluate_policy_gate",
    "dashboard_get_policy_gate_evaluation",
}

_BANNED = {
    "dashboard_promote_policy",
    "dashboard_activate_policy",
    "dashboard_set_live_policy",
    "dashboard_rollback_live_policy",
    "dashboard_record_policy_governance_decision",
    "dashboard_record_governance_decision",
}


def _tool_names(server) -> set[str]:
    if hasattr(server, "list_tools_sync"):
        tools = server.list_tools_sync()
    else:
        tools = server._tool_manager.list_tools()
    return {t.name for t in tools}


def test_policy_replay_mcp_tools_registered() -> None:
    names = _tool_names(create_mcp_server())
    missing = _REQUIRED - names
    assert not missing, f"missing MCP tools: {sorted(missing)}; got {sorted(names)}"


def test_policy_replay_orchestrator_manifest_includes_tools() -> None:
    manifest = build_orchestrator_tool_manifest()
    names = {row["function"]["name"] for row in manifest}
    missing = _REQUIRED - names
    assert not missing, f"missing orchestrator tools: {sorted(missing)}"


def test_mcp_has_no_activation_or_decision_write_tools() -> None:
    names = _tool_names(create_mcp_server())
    present = _BANNED & names
    assert not present, f"banned tools must not be registered: {sorted(present)}"
    for name in names:
        lowered = name.lower()
        assert "promote" not in lowered
        assert "activate" not in lowered
        assert "set_live" not in lowered
        assert "rollback_live" not in lowered
        assert "governance_decision" not in lowered
