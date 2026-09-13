"""Hosted digiquant-mcp defaults: read-scope only off localhost (Phase 2 Track D).

The hosted container (`digiquant/Dockerfile.mcp` + `DigiQuantMcpContainer.envVars`
in the stack Worker) must resolve `DIGIQUANT_MCP_SCOPE` to `read`; `full` never
leaves localhost. Local `python -m digiquant.mcp_server` keeps defaulting to
`full` (pinned here so the hosted default cannot leak into the library default).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_MCP = REPO_ROOT / "digiquant" / "Dockerfile.mcp"
STACK_INDEX_TS = REPO_ROOT / "cloudflare" / "digithings-stack-cloudflare" / "src" / "index.ts"
MCP_SERVER_PY = REPO_ROOT / "digiquant" / "src" / "digiquant" / "mcp_server.py"

HOSTED_SCOPE_LINE = "ENV DIGIQUANT_MCP_SCOPE=read"
HOSTED_ENVVAR_LINE = 'DIGIQUANT_MCP_SCOPE: env.DIGIQUANT_MCP_SCOPE ?? "read"'
ENV_INTERFACE_LINE = "DIGIQUANT_MCP_SCOPE?: string;"
LOCAL_SCOPE_DEFAULT = 'default=os.environ.get("DIGIQUANT_MCP_SCOPE", "full")'


@pytest.mark.unit
def test_hosted_image_defaults_scope_to_read():
    text = DOCKERFILE_MCP.read_text(encoding="utf-8")
    assert HOSTED_SCOPE_LINE in text


@pytest.mark.unit
def test_stack_container_passes_scope_through_default_read():
    # Asserted on file text: DigiQuantMcpContainer is a Cloudflare Container /
    # Durable Object, not constructible outside the Workers runtime (same reason
    # env-vars-pin.test.js reads index.ts as text).
    text = STACK_INDEX_TS.read_text(encoding="utf-8")
    assert HOSTED_ENVVAR_LINE in text


@pytest.mark.unit
def test_stack_env_interface_declares_scope():
    text = STACK_INDEX_TS.read_text(encoding="utf-8")
    assert ENV_INTERFACE_LINE in text


@pytest.mark.unit
def test_local_mcp_server_default_scope_stays_full():
    text = MCP_SERVER_PY.read_text(encoding="utf-8")
    assert LOCAL_SCOPE_DEFAULT in text
