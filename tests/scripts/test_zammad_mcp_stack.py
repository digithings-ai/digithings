"""Pins for the zammad-mcp program inside the digithings-stack container."""

from __future__ import annotations

import subprocess
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


def test_entrypoint_guards_the_etc_hosts_write():
    """The alias write must be best-effort (#4149).

    It runs under `set -eu` immediately before `exec supervisord`, so an
    unguarded redirect aborts PID 1: `:8000` never opens and the Worker 503s
    every request.
    """
    writes = [
        line
        for line in _code_lines(ENTRYPOINT).replace("\\\n", " ").splitlines()
        if "/etc/hosts" in line and ">>" in line
    ]
    assert writes, "expected the /etc/hosts alias write"
    for line in writes:
        guarded = "||" in line or line.lstrip().startswith("if ")
        assert guarded, f"/etc/hosts write is unguarded: {line.strip()}"


def test_a_failing_redirect_aborts_set_e_unless_guarded(tmp_path):
    """Pins the shell semantics the guard depends on, so the reasoning cannot rot."""
    target = tmp_path / "no-such-dir" / "hosts"
    guarded = f"set -eu\nprintf 'x\\n' >> {target} 2>/dev/null || echo WARN\necho REACHED\n"
    unguarded = f"set -eu\nprintf 'x\\n' >> {target} 2>/dev/null\necho REACHED\n"
    ok = subprocess.run(["sh", "-c", guarded], capture_output=True, text=True)
    aborted = subprocess.run(["sh", "-c", unguarded], capture_output=True, text=True)
    assert ok.returncode == 0 and "REACHED" in ok.stdout
    assert aborted.returncode != 0 and "REACHED" not in aborted.stdout


def test_stack_dockerfile_ships_the_mcp_package():
    body = _code_lines(STACK_DOCKERFILE)
    assert "COPY scripts/zammad_mcp ./scripts/zammad_mcp" in body


def test_stack_container_env_passes_the_zammad_token():
    source = STACK_INDEX.read_text()
    assert 'ZAMMAD_API_TOKEN: env.ZAMMAD_API_TOKEN ?? ""' in source
    assert "ZAMMAD_API_TOKEN?: string;" in source


def test_wrangler_documents_the_zammad_secret():
    assert "ZAMMAD_API_TOKEN" in WRANGLER.read_text()


def test_digiproject_allowlist_excludes_zammad():
    """The website digichat must not offer Zammad from the shared allowlist.

    OCC reaches the read-only ticket tools per request instead, through the
    live MCP union over X-Digi-Mcp-Servers (tool_policy.apply_mcp_extra_tools).
    """
    digiproject = REPO_ROOT / "infra" / "digichat-release" / "config" / "digiproject.yaml"
    assert "zammad" not in _code_lines(digiproject)


def test_entrypoint_allowed_tools_fallback_excludes_zammad():
    """The container's real DIGI_ALLOWED_TOOLS fallback stays in sync (#2306)."""
    exports = [
        line
        for line in _code_lines(ENTRYPOINT).splitlines()
        if line.startswith("export DIGI_ALLOWED_TOOLS=")
    ]
    assert exports, "expected the DIGI_ALLOWED_TOOLS export"
    for line in exports:
        assert "zammad" not in line
