"""Pins that the digithings-stack base platform no longer carries zammad-mcp.

The OCC Zammad MCP now runs inside the digichat image and is served by the
digichat worker at ``https://digithings.ai/api/mcp/zammad/mcp`` (commits
e855b6c3be + a412e07b46). It was removed from the base stack (supervisord
program, entrypoint /etc/hosts alias, Dockerfile COPY, container env). These
pins are deliberately inverted from the "stack carries zammad" form so a stale
re-add fails here — the removal's whole point is that the base platform must
not run it again.

Assertions that were never about the stack's copy are kept as-is: the guard
semantics of the remaining /etc/hosts write, the digiproject allowlist, the
entrypoint tools fallback, and the MCP module's own aggregate tool (which the
digichat image still serves).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_DIR = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
SUPERVISORD = STACK_DIR / "container" / "supervisor" / "supervisord.conf"
ENTRYPOINT = STACK_DIR / "container" / "entrypoint.sh"
STACK_INDEX = STACK_DIR / "src" / "index.ts"
STACK_DOCKERFILE = REPO_ROOT / "infra/docker/Dockerfile.digithings-stack-cloudflare"
WRANGLER = STACK_DIR / "wrangler.toml"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


def _code_lines(path: Path) -> str:
    """File body with full-line comments stripped (assertions target code)."""
    lines = [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


def test_supervisord_no_longer_runs_zammad_mcp():
    body = _code_lines(SUPERVISORD)
    assert "[program:zammad-mcp]" not in body
    assert "scripts.zammad_mcp.server" not in body
    assert "ZAMMAD_MCP_HOST" not in body
    assert "ZAMMAD_MCP_ALLOWED_HOSTS" not in body
    assert "zammad-mcp.log" not in body


def test_entrypoint_no_longer_aliases_the_dotless_mcp_host():
    body = _code_lines(ENTRYPOINT)
    assert "zammad-mcp" not in body
    assert "zammad_mcp" not in body


def test_entrypoint_guards_the_etc_hosts_write():
    """Every /etc/hosts alias write must be best-effort (#4149).

    The remaining alias is the `valkey` one (searxng limiter DB, #4297). It
    runs under `set -eu` immediately before `exec supervisord`, so an
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


def test_stack_dockerfile_no_longer_ships_the_mcp_package():
    body = _code_lines(STACK_DOCKERFILE)
    assert "COPY scripts/zammad_mcp" not in body


def test_dockerignore_still_reincludes_the_mcp_package():
    """The digichat image builds from the repo root and needs the package.

    Removing the COPY from the stack Dockerfile must NOT strip the re-include:
    infra/docker/Dockerfile.digichat-cloudflare still does `COPY scripts/zammad_mcp`, so a
    dropped re-include would silently break the digichat OCC MCP build.
    """
    assert "!scripts/zammad_mcp" in _code_lines(DOCKERIGNORE)


def test_stack_container_env_no_longer_passes_the_zammad_token():
    source = STACK_INDEX.read_text()
    assert "ZAMMAD_API_TOKEN" not in source


def test_wrangler_no_longer_documents_the_zammad_secret():
    """The in-repo secret checklist must not send an operator to ZAMMAD_API_TOKEN.

    The secret may still exist on the deployed worker (this slice does not
    touch Cloudflare), but nothing in the stack reads it, so the wrangler
    comment is a stale pointer to a removed program.
    """
    assert "ZAMMAD_API_TOKEN" not in WRANGLER.read_text()


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


def test_mcp_registers_aggregate_tool():
    """The zammad-mcp module still serves the analytics ranking tool (#4717).

    It is the digichat image that runs it now; the module itself is unchanged.

    ``ToolManager.list_tools()`` (public sync API) rather than the private
    ``_tools`` dict — same names either way, robust across mcp builds.
    """
    pytest.importorskip("mcp.server.fastmcp")
    from scripts.zammad_mcp import server

    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert {
        "search_tickets",
        "list_tickets",
        "get_ticket",
        "ticket_report",
        "aggregate_tickets",
    } <= names


def test_aggregate_delegates_to_digisearch_tables():
    """Generalization requirement (#4717): one counting/enrichment implementation.

    ``scripts/zammad_mcp/aggregate.py`` reuses ``digisearch.core.tables``
    (``group_count``/``enrich_rows``), not a second copy of the same logic.
    """
    body = (REPO_ROOT / "scripts" / "zammad_mcp" / "aggregate.py").read_text()
    assert "from digisearch.core.tables import" in body
    assert "group_count" in body
    assert "enrich_rows" in body
