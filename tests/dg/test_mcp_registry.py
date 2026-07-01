"""Unit tests for register_mcp_server() — OpenBB MCP server registration (issue #401)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from digigraph.orchestration.registry import ToolExposureMode, register_mcp_server


@pytest.fixture()
def mcp_config(tmp_path: Path) -> Path:
    """Write a minimal mcp_servers.yaml to a temp directory and return its path."""
    cfg = tmp_path / "mcp_servers.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        mcp_servers:
          openbb:
            description: "OpenBB financial data MCP server"
            enabled: true
            tool_exposure_mode: summary
            free_providers:
              - name: yfinance
                enabled: true
              - name: fred
                enabled: true
                api_key_env: FRED_API_KEY
                optional: true
              - name: sec_edgar
                enabled: true
              - name: fama_french
                enabled: true
            premium_providers:
              - name: intrinio
                enabled_if_env: INTRINIO_API_KEY
              - name: benzinga
                enabled_if_env: BENZINGA_API_KEY
              - name: polygon
                enabled_if_env: POLYGON_API_KEY
        """)
    )
    return cfg


@pytest.mark.unit
def test_free_providers_enabled_without_keys(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """yfinance, fred, sec_edgar, fama_french are returned even when no premium keys are set."""
    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)
    monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    # FRED_API_KEY is optional — should not affect free-provider inclusion.
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    result = register_mcp_server("openbb", config_path=str(mcp_config))

    names = {d["name"] for d in result}
    assert "openbb__yfinance" in names
    assert "openbb__fred" in names
    assert "openbb__sec_edgar" in names
    assert "openbb__fama_french" in names


@pytest.mark.unit
def test_premium_providers_skipped_without_keys(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Premium providers are excluded when their env vars are absent."""
    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)
    monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    result = register_mcp_server("openbb", config_path=str(mcp_config))

    names = {d["name"] for d in result}
    assert "openbb__intrinio" not in names
    assert "openbb__benzinga" not in names
    assert "openbb__polygon" not in names


@pytest.mark.unit
def test_premium_provider_included_when_key_set(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A premium provider is included when its env var is set."""
    monkeypatch.setenv("INTRINIO_API_KEY", "test-key-value")
    monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)

    result = register_mcp_server("openbb", config_path=str(mcp_config))

    names = {d["name"] for d in result}
    assert "openbb__intrinio" in names
    assert "openbb__benzinga" not in names


@pytest.mark.unit
def test_summary_mode_used_by_default(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default mode is SUMMARY: descriptors have 'name', 'description', 'provider', 'server'
    keys but NOT the full OpenAI 'type'/'function' keys."""
    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)

    result = register_mcp_server("openbb", config_path=str(mcp_config))

    assert result, "Expected at least one descriptor"
    first = result[0]
    assert "name" in first
    assert "description" in first
    assert "provider" in first
    assert "server" in first
    # SUMMARY should NOT include OpenAI function-tool schema keys.
    assert "type" not in first
    assert "function" not in first


@pytest.mark.unit
def test_detailed_mode_returns_openai_schema(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DETAILED mode returns OpenAI function-tool schema with 'type' and 'function' keys."""
    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)

    result = register_mcp_server(
        "openbb", config_path=str(mcp_config), mode=ToolExposureMode.DETAILED
    )

    assert result, "Expected at least one descriptor"
    first = result[0]
    assert first.get("type") == "function"
    assert "function" in first
    assert "name" in first["function"]
    assert "description" in first["function"]
    assert "parameters" in first["function"]


@pytest.mark.unit
def test_missing_config_returns_empty(tmp_path: Path) -> None:
    """When the config file doesn't exist, return an empty list (no exception)."""
    result = register_mcp_server(
        "openbb", config_path=str(tmp_path / "nonexistent.yaml")
    )
    assert result == []


@pytest.mark.unit
def test_unknown_server_name_returns_empty(mcp_config: Path) -> None:
    """When the requested server name is not in the config, return an empty list."""
    result = register_mcp_server("unknown_server", config_path=str(mcp_config))
    assert result == []


@pytest.mark.unit
def test_register_mcp_server_does_not_wire_tools_into_registry(
    mcp_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REM-100 / #401: descriptors only — must not call register_tool() yet."""
    from digigraph.orchestration.registry import list_tool_names

    monkeypatch.delenv("INTRINIO_API_KEY", raising=False)
    before = set(list_tool_names())
    descriptors = register_mcp_server("openbb", config_path=str(mcp_config))
    assert descriptors, "expected descriptors for wiring tests"
    after = set(list_tool_names())
    assert before == after


@pytest.mark.unit
def test_disabled_server_returns_empty(tmp_path: Path) -> None:
    """When the server's 'enabled' flag is false, return an empty list."""
    cfg = tmp_path / "mcp_servers.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        mcp_servers:
          openbb:
            description: "disabled server"
            enabled: false
            free_providers:
              - name: yfinance
                enabled: true
            premium_providers: []
        """)
    )
    result = register_mcp_server("openbb", config_path=str(cfg))
    assert result == []
