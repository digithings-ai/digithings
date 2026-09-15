"""Pins for the zammad-mcp program inside the digithings-stack container."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_DIR = REPO_ROOT / "cloudflare" / "digithings-stack-cloudflare"
SUPERVISORD = STACK_DIR / "container" / "supervisor" / "supervisord.conf"
ENTRYPOINT = STACK_DIR / "container" / "entrypoint.sh"
STACK_INDEX = STACK_DIR / "src" / "index.ts"
STACK_DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
WRANGLER = STACK_DIR / "wrangler.toml"


def _code_lines(path: Path) -> str:
    """File body with full-line comments stripped (assertions target code)."""
    lines = [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def test_supervisord_runs_zammad_mcp():
    body = _code_lines(SUPERVISORD)
    assert "[program:zammad-mcp]" in body
    assert "python -m scripts.zammad_mcp.server --port 8770" in body
    assert 'ZAMMAD_MCP_HOST="0.0.0.0"' in body
    assert 'ZAMMAD_MCP_ALLOWED_HOSTS="zammad-mcp"' in body
    assert "/var/log/supervisor/zammad-mcp.log" in body


def test_entrypoint_aliases_the_dotless_mcp_host():
    body = _code_lines(ENTRYPOINT)
    assert "zammad-mcp" in body
    assert "/etc/hosts" in body


def test_stack_dockerfile_ships_the_mcp_package():
    body = _code_lines(STACK_DOCKERFILE)
    assert "COPY scripts/zammad_mcp ./scripts/zammad_mcp" in body


def test_stack_container_env_passes_the_zammad_token():
    source = STACK_INDEX.read_text()
    assert 'ZAMMAD_API_TOKEN: env.ZAMMAD_API_TOKEN ?? ""' in source
    assert "ZAMMAD_API_TOKEN?: string;" in source


def test_wrangler_documents_the_zammad_secret():
    assert "ZAMMAD_API_TOKEN" in WRANGLER.read_text()
