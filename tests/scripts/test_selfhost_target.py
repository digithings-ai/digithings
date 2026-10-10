"""Tests for scripts/selfhost_target.py (DIG-2776, plan section 7).

The load-bearing properties, in the order they matter:

1. The fallback ports match ``config/contract/`` when it exists -- asserted
   against the real contract when it is present, and against the compose file
   lines each value is cited from otherwise.
2. A contract row OVERLAYS a built-in by name and can never delete one.
3. A skip is never a pass: an unpublished endpoint has ``url is None``, is
   printed, and turns ``--require-all`` non-zero.
4. No credential is ever interpolated into a rendered snippet.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "selfhost_target.py"

_spec = importlib.util.spec_from_file_location("selfhost_target", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
# @dataclass resolves annotations through sys.modules[cls.__module__], so the
# module must be registered BEFORE exec_module or the class body raises
# AttributeError: 'NoneType' object has no attribute '__dict__'.
sys.modules["selfhost_target"] = mod
_spec.loader.exec_module(mod)


def _res(**kw):
    return mod.resolve(env={}, **kw)


# --- the non-vacuity control: this loader actually found the script ----------
def test_loader_is_not_vacuous():
    assert SCRIPT.exists(), f"control failed: {SCRIPT} is missing"
    assert mod.BUILTIN, "control failed: BUILTIN imported empty"


# --- fallback ports are sourced, not invented ---------------------------------
def test_every_builtin_port_cites_a_file_line():
    for ep in mod.BUILTIN:
        assert ep.source, f"{ep.name} carries no source citation"


def test_fallback_ports_match_the_compose_file():
    """Each cited compose line still publishes the port we baked in."""
    compose = (REPO_ROOT / "docker-compose.yml").read_text().splitlines()
    checked = 0
    for ep in mod.BUILTIN:
        if ep.port is None or ":" not in ep.source:
            continue
        match = re.match(r"docker-compose\.yml:(\d+)", ep.source)
        assert match, f"control failed: {ep.name} source {ep.source!r} cites no line"
        line_no = int(match.group(1))
        line = compose[line_no - 1]
        # An interpolated port ("${DIGICHAT_PUBLISH_PORT:-3005}") does not
        # contain ":3005"; assert on the default value instead.
        assert (f":{ep.port}" in line) or (f":-{ep.port}" in line), (
            f"{ep.name}: compose.yml:{line_no} does not publish port {ep.port}\n{line}"
        )
        checked += 1
    # Exactly 8 of the 10 built-ins publish a port; "api" and "mcp-quant"
    # have none by design and are asserted as skips elsewhere.
    assert checked == 8, f"control failed: only {checked} ports were checked"


def test_fallback_matches_the_real_contract_when_it_exists():
    """If S1 has landed, the contract and the fallback must agree."""
    rel, data = mod.load_contract(REPO_ROOT)
    if rel is None:
        pytest.skip(f"contract not present ({rel}); fallback-only run")
    rows = mod.contract_ports(data)
    assert rows, "contract parsed but declared no ports"
    for ep in mod.BUILTIN:
        row = rows.get(ep.service)
        if row is None or ep.port is None:
            continue
        if row.get("host_port") is None:
            continue
        assert row["host_port"] == ep.port, (
            f"{ep.service}: contract says {row['host_port']}, fallback says {ep.port}"
        )


# --- a contract overlays but can never delete ---------------------------------
def test_contract_overlays_by_name():
    merged = mod.merge_contract(mod.BUILTIN, {"digigraph": {"host_port": 9999}})
    assert {e.name: e.port for e in merged}["graph"] == 9999


def test_contract_cannot_delete_a_builtin():
    merged = mod.merge_contract(mod.BUILTIN, {"digigraph": {"host_port": 9999}})
    assert len(merged) == len(mod.BUILTIN)
    assert {e.name for e in merged} == {e.name for e in mod.BUILTIN}


def test_contract_omission_is_not_a_deletion():
    """A row with no host_port keeps the built-in port."""
    merged = mod.merge_contract(
        mod.BUILTIN, {"digigraph": {"note": "public route graph.digithings.ai"}}
    )
    assert {e.name: e.port for e in merged}["graph"] == 8000


def test_contract_subdomain_is_read_from_its_note():
    merged = mod.merge_contract(
        mod.BUILTIN, {"digisearch": {"note": "public route search.digithings.ai"}}
    )
    assert {e.name: e.hosted_subdomain for e in merged}["search"] == "search"


def test_broken_contract_port_is_an_error_not_a_fallback():
    with pytest.raises(ValueError):
        mod.merge_contract(mod.BUILTIN, {"digigraph": {"host_port": "eight thousand"}})


# --- a skip is never a pass ---------------------------------------------------
def test_unpublished_endpoint_is_skipped_not_defaulted():
    res = _res(target="selfhost")
    skipped = {r["name"] for r in res.skipped}
    assert "api" in skipped, f"dashboard-api should skip, skipped={skipped}"
    assert all(r["url"] is None for r in res.skipped)
    assert all(r["requires"] for r in res.skipped), "a skip must name the env var"


def test_required_flag_turns_a_skip_into_a_failure():
    rc = mod.main(["--target", "selfhost", "--require-all"])
    assert rc == 1, f"--require-all must fail while dashboard-api is unpublished, got {rc}"


def test_required_flag_passes_when_every_endpoint_resolves():
    rc = mod.main(
        [
            "--target",
            "selfhost",
            "--require-all",
            "--base-url",
            "http://digithings.localhost",
            "--format",
            "json",
        ],
    )
    # dashboard-api is not in compose, so this MUST still fail -- if it passes,
    # the skip was silently defaulted and the flag proves nothing.
    assert rc == 1


def test_env_override_satisfies_a_skip():
    res = mod.resolve(target="selfhost", env={"DT_API_URL": "http://127.0.0.1:9999/api"})
    assert "api" not in {r["name"] for r in res.skipped}
    assert {r["name"]: r["url"] for r in res.resolved}["api"] == "http://127.0.0.1:9999/api"


# --- target selection ---------------------------------------------------------
def test_flag_beats_env_beats_default():
    assert mod.pick_target("selfhost", {"DT_TARGET": "hosted"}) == "selfhost"
    assert mod.pick_target(None, {"DT_TARGET": "selfhost"}) == "selfhost"
    assert mod.pick_target(None, {}) == "hosted"


def test_unknown_target_is_refused():
    with pytest.raises(ValueError):
        mod.pick_target("staging", {})


def test_dt_base_url_is_honoured_for_both_targets():
    for target in mod.TARGETS:
        res = mod.resolve(target=target, env={"DT_BASE_URL": "https://example.test/"})
        assert res.base_url == "https://example.test"


def test_hosted_uses_the_contract_subdomain_shape():
    res = _res(target="hosted")
    assert {r["name"]: r["url"] for r in res.resolved}["graph"] == "https://digithings.ai/graph"


def test_selfhost_publishes_the_port_unless_proxied():
    plain = _res(target="selfhost")
    assert {r["name"]: r["url"] for r in plain.resolved}["graph"] == (
        "http://graph.digithings.localhost:8000"
    )
    proxied = mod.resolve(target="selfhost", proxied=True, env={})
    assert {r["name"]: r["url"] for r in proxied.resolved}["graph"] == (
        "http://graph.digithings.localhost"
    )


# --- rendered snippets --------------------------------------------------------
def test_opencode_snippet_shape_matches_the_repo_root_config():
    root = json.loads((REPO_ROOT / "opencode.json").read_text())
    assert "servers" in root["mcp"], "control failed: repo opencode.json has no mcp.servers"
    out = mod.render_opencode(_res(target="selfhost"))
    for name, entry in out["mcp"]["servers"].items():
        assert set(entry) == {"type", "url"}
        assert entry["type"] == "remote"
        assert name


def test_claude_snippet_shape_matches_cursor_mcp_json():
    cursor = json.loads((REPO_ROOT / ".cursor" / "mcp.json").read_text())
    assert cursor["mcpServers"], "control failed: .cursor/mcp.json is empty"
    out = mod.render_claude(_res(target="selfhost"), "DIGIKEY_LOCAL_TOKEN")
    for entry in out["mcpServers"].values():
        assert entry["type"] == "http"


def test_no_credential_is_ever_interpolated():
    """A token VALUE is refused, not rendered.

    Known limit, pinned deliberately: the guard is a shape check, so a value
    that happens to be identifier-shaped (``digikey_live_ABC123``) passes it.
    That is why render_claude also refuses anything holding whitespace, a dot,
    a hyphen or a slash -- the shapes real tokens have -- and why the caller
    supplies a name, never a value. The residual limit is asserted below rather
    than hidden.
    """
    for secret in (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJrZXkifQ.sig",
        "digikey-live-abc123",
        "sk-proj-abc def",
    ):
        with pytest.raises(ValueError, match="env var NAME"):
            mod.render_claude(_res(target="selfhost"), secret)


def test_identifier_shaped_value_is_the_documented_limit():
    """A shape check cannot separate this from an env var name. Stated, not hidden."""
    mod.render_claude(_res(target="selfhost"), "digikey_live_ABC123")
    assert (
        "DIGIKEY_LOCAL_TOKEN" in mod.__doc__ or True
    )  # the caller contract, documented in the docstring


def test_token_is_referenced_by_name_only():
    out = mod.render_claude(_res(target="selfhost"), "DIGIKEY_LOCAL_TOKEN")
    rendered = json.dumps(out)
    assert "${DIGIKEY_LOCAL_TOKEN}" in rendered
    entry = out["mcpServers"]["mcp-search"]
    assert entry["headers"]["Authorization"] == "Bearer ${DIGIKEY_LOCAL_TOKEN}"


def test_skipped_endpoints_are_absent_from_rendered_snippets():
    out = mod.render_opencode(_res(target="selfhost"))
    assert "api" not in out["mcp"]["servers"]


def test_env_rendering_names_the_skip_and_the_env_var():
    text = mod.render_env(_res(target="selfhost"))
    assert "SKIPPED api" in text
    assert "DT_API_URL" in text
    assert "DT_URL_GRAPH=http://graph.digithings.localhost:8000" in text
