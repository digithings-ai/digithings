"""Unit tests for the dedicated digiquant-mcp container + hosting wiring (#3780, Task 8).

The hosted market-data MCP server is a dedicated container built from
``digiquant/Dockerfile.mcp`` (FastMCP ``streamable-http`` on :8767 with the
``[research]``/``[mcp]`` extras — never the backtest engine), fronted by a
second Cloudflare Container (``DigiQuantMcpContainer``) beside the Profile A
stack in ``frontend/digithings-stack-cloudflare/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "digiquant" / "Dockerfile.mcp"
WRANGLER = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "wrangler.toml"
WORKER_INDEX = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "src" / "index.ts"
WORKER_PORTS = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "src" / "ports.ts"
ARCHITECTURE = REPO_ROOT / "digiquant" / "ARCHITECTURE.md"


def test_mcp_dockerfile_serves_streamable_http():
    text = DOCKERFILE.read_text()
    assert "8767" in text
    assert "streamable-http" in text or "run_mcp" in text
    assert "nautilus" not in text


def test_mcp_dockerfile_pins_and_entrypoint() -> None:
    text = DOCKERFILE.read_text()
    assert "python:3.12" in text
    assert "--extra research" in text
    assert "--extra mcp" in text
    assert "EXPOSE 8767" in text
    assert "digiquant.mcp_server" in text
    assert "DIGIQUANT_MCP_HOST" in text
    assert "DIGIQUANT_MCP_PORT" in text


def test_wrangler_wires_dedicated_mcp_container() -> None:
    text = WRANGLER.read_text()
    assert "digiquant/Dockerfile.mcp" in text
    assert "DigiQuantMcpContainer" in text
    assert "MCP_STACK" in text


def test_worker_routes_mcp_service() -> None:
    index = WORKER_INDEX.read_text()
    assert "DigiQuantMcpContainer" in index
    assert "DIGIQUANT_MCP_PORT" in index
    assert "_stack/mcp" in index
    ports = WORKER_PORTS.read_text()
    assert "8767" in ports
    assert "DIGIQUANT_MCP_PORT" in ports


def test_wrangler_documents_mcp_secrets() -> None:
    text = WRANGLER.read_text()
    for name in (
        "FRED_API_KEY",
        "R2_ACCOUNT_ID",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
    ):
        assert name in text, name


def test_architecture_documents_mcp_hosting() -> None:
    text = ARCHITECTURE.read_text()
    assert "mcp.digithings.ai" in text
    assert "digiquant:backtest" in text
    assert "DigiQuantMcpContainer" in text
