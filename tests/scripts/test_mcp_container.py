"""Unit tests for the dedicated digiquant-mcp container + hosting wiring (#3780, Task 8).

The hosted market-data MCP server is a dedicated container built from
``digiquant/Dockerfile.mcp`` (FastMCP ``streamable-http`` on :8767 with the
``[research]``/``[mcp]`` extras — never the backtest engine), fronted by a
second Cloudflare Container (``DigiQuantMcpContainer``) beside the Profile A
stack in ``frontend/digithings-stack-cloudflare/``.

RED premise (review finding 3): at creation these tests failed with
``FileNotFoundError`` (brief Step 2) because ``Dockerfile.mcp`` did not exist
yet — file-absence RED applied then and only then. After creation every test
below asserts behavior semantics, so a regression fails by assertion, not by
absence: Dockerfile assertions run against the comment-stripped body
(``_code_lines``), so header-comment tokens alone can never satisfy them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "digiquant" / "Dockerfile.mcp"
WRANGLER = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "wrangler.toml"
WORKER_INDEX = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "src" / "index.ts"
WORKER_PORTS = REPO_ROOT / "frontend" / "digithings-stack-cloudflare" / "src" / "ports.ts"
ARCHITECTURE = REPO_ROOT / "digiquant" / "ARCHITECTURE.md"

#: Vars forwarded by DigiQuantMcpContainer.envVars only — never duplicated into
#: DigiStackContainer.envVars (review finding 6).
MCP_SCOPED_VARS = (
    "DIGIQUANT_MARKET_DATA_BACKEND",
    "FRED_API_KEY",
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)


def _code_lines(path: Path) -> str:
    """File text minus full-line ``#`` comments (review finding 5).

    Behavior lives in Dockerfile instructions, not the header comment — a test
    that passes on comment tokens (``streamable-http``/``run_mcp`` appear only
    in the header) cannot catch a regressed body.
    """
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


def _env_vars_blocks(source: str) -> list[str]:
    """Both ``envVars = { ... };`` blocks in index.ts: [stack, mcp]."""
    return [m.group(1) for m in re.finditer(r"envVars = \{([\s\S]*?)\n {2}\};", source)]


def test_mcp_dockerfile_serves_streamable_http():
    body = _code_lines(DOCKERFILE)
    assert "8767" in body
    # Entrypoint semantics on the body, not header-comment tokens (finding 5):
    # the module whose run_mcp() serves streamable-http must be the CMD target.
    assert "digiquant.mcp_server" in body
    assert "nautilus" not in body.lower()


def test_mcp_dockerfile_pins_and_entrypoint() -> None:
    body = _code_lines(DOCKERFILE)
    assert "python:3.12" in body
    assert "[research,mcp]" in body
    assert "uv pip install --system" in body
    assert "EXPOSE 8767" in body
    assert "digiquant.mcp_server" in body
    assert "DIGIQUANT_MCP_HOST" in body
    assert "DIGIQUANT_MCP_PORT" in body
    assert "0.0.0.0" in body


def test_mcp_dockerfile_builds_from_repo_root() -> None:
    """`docker build -f digiquant/Dockerfile.mcp .` from the repo root (finding 2).

    `uv sync --frozen` needs the workspace root + uv.lock in context, which a
    COPY-digiquant-only body never provides. The body therefore mirrors
    digiquant/Dockerfile: per-package COPYs (workspace deps first so pip
    resolves them locally) + `uv pip install --system -e`, no frozen sync.
    """
    body = _code_lines(DOCKERFILE)
    assert "uv sync --frozen" not in body
    for manifest in (
        "digibase/pyproject.toml",
        "digikey/pyproject.toml",
        "digiquant/pyproject.toml",
    ):
        assert manifest in body, manifest


def test_mcp_dockerfile_copy_sources_exist_from_repo_root() -> None:
    """Every COPY source resolves from the repo root (construction guard)."""
    body = _code_lines(DOCKERFILE)
    copies = [ln.split() for ln in body.splitlines() if ln.strip().startswith("COPY ")]
    assert copies
    for parts in copies:
        for src in parts[1:-1]:
            assert (REPO_ROOT / src).exists(), src


def test_wrangler_wires_dedicated_mcp_container() -> None:
    text = WRANGLER.read_text()
    assert "digiquant/Dockerfile.mcp" in text
    assert "DigiQuantMcpContainer" in text
    assert "MCP_STACK" in text


def test_worker_routes_mcp_service() -> None:
    index = WORKER_INDEX.read_text()
    assert "DigiQuantMcpContainer" in index
    assert "DIGIQUANT_MCP_PORT" in index
    # Finding 1: no live unauthenticated forwarding route ships. The workers.dev
    # `/_stack/mcp` path forwarder is removed (Worker-edge digikey enforcement
    # is a separate prod-gate follow-up); the commented mcp.digithings.ai route
    # stays reserved, not live. Comments may name the removed path only to
    # record its removal, so this pins the quoted route literals, not the words.
    assert '"/_stack/mcp"' not in index
    assert '"/_stack/mcp/"' not in index
    # Finding 4: hostname routing is the exact reserved hostname, never a
    # `startsWith("mcp.")` prefix matching any mcp.* host.
    assert 'startsWith("mcp.")' not in index
    assert "startsWith('mcp.')" not in index
    assert "DIGIQUANT_MCP_HOSTNAME" in index
    ports = WORKER_PORTS.read_text()
    assert "8767" in ports
    assert "DIGIQUANT_MCP_PORT" in ports


def test_stack_container_env_has_no_mcp_duplication() -> None:
    """Finding 6: MCP secrets live on DigiQuantMcpContainer.envVars only."""
    blocks = _env_vars_blocks(WORKER_INDEX.read_text())
    assert len(blocks) == 2
    stack_block, mcp_block = blocks
    for name in MCP_SCOPED_VARS:
        assert f"{name}:" not in stack_block, name
        assert f"{name}:" in mcp_block, name


def test_mcp_container_backend_passthrough_matches_library_default() -> None:
    """Finding 7: no silent default flip — unset/empty keeps library behavior."""
    mcp_block = _env_vars_blocks(WORKER_INDEX.read_text())[1]
    entry = next(ln for ln in mcp_block.splitlines() if "DIGIQUANT_MARKET_DATA_BACKEND" in ln)
    assert '"r2"' not in entry
    assert '?? ""' in entry


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
