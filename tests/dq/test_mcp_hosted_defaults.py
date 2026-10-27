"""Hosted digiquant-mcp defaults: read-scope only off localhost (Phase 2 Track D).

The hosted image (`digiquant/Dockerfile.mcp`) resolves `DIGIQUANT_MCP_SCOPE` to
`read`; `full` never leaves localhost. The Cloudflare Container that forwarded it
(`DigiQuantMcpContainer.envVars` in the stack Worker) was deleted in DIG-5558 —
the hosted read path is the Worker-native `DigiQuantMcpAgent` — so that wiring is
pinned as an absence. Local `python -m digiquant.mcp_server` keeps defaulting to
`full` (pinned here so the hosted default cannot leak into the library default).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_MCP = REPO_ROOT / "digiquant" / "Dockerfile.mcp"
STACK_INDEX_TS = REPO_ROOT / "apps" / "digithings-stack-cloudflare" / "src" / "index.ts"
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
def test_the_deleted_stack_container_no_longer_forwards_scope():
    # Asserted on file text: the removed class was a Cloudflare Container /
    # Durable Object, not constructible outside the Workers runtime (same reason
    # env-vars-pin.test.js reads index.ts as text). DIG-5558 deleted it, so the
    # hosted scope default is no longer a container concern.
    text = STACK_INDEX_TS.read_text(encoding="utf-8")
    assert HOSTED_ENVVAR_LINE not in text
    assert "DigiQuantMcpContainer" not in text


@pytest.mark.unit
def test_stack_env_interface_declares_scope():
    text = STACK_INDEX_TS.read_text(encoding="utf-8")
    assert ENV_INTERFACE_LINE in text


@pytest.mark.unit
def test_local_mcp_server_default_scope_stays_full():
    text = MCP_SERVER_PY.read_text(encoding="utf-8")
    assert LOCAL_SCOPE_DEFAULT in text
