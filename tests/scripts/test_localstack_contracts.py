"""Catalogue and preflight tests for the local self-host stack (DIG-2775, S7).

Two properties matter here. Every built-in default URL must trace to a source
in the tree, so a check cannot silently point at a port nothing serves; and a
preflight that finds nothing wrong must be proven able to find something.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.localstack import contracts, preflight

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- the catalogue is sourced, and the sources still exist -------------------


def test_every_builtin_check_carries_a_source():
    for check in contracts.BUILTIN_CHECKS:
        assert check.source, f"{check.name} has no source"


def test_builtin_urls_are_labelled_local_loopback():
    """A default must never point anywhere but the developer's own machine."""
    for check in contracts.BUILTIN_CHECKS:
        if check.url is not None:
            assert check.url.startswith("http://127.0.0.1:") or check.url.startswith(
                "http://localhost:"
            ), f"{check.name} defaults off-loopback: {check.url}"


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("digikey", "digikey/src/digikey/server.py"),
        ("digigraph", "digigraph/src/digigraph/server.py"),
        ("digisearch", "digisearch/src/digisearch/server.py"),
        ("digivault", "digivault/src/digivault/server.py"),
        ("digitrace", "digitrace/src/digitrace/server.py"),
        ("dashboard-api", "apps/dashboard-api/src/index.ts"),
    ],
)
def test_the_source_file_a_check_cites_still_exists(name, path):
    """The source string is only evidence if the file it names is really there.

    Control: the same loop over ``REPO_ROOT`` finds ``README.md``, so a miss
    here is a missing file and not a broken finder.
    """
    assert (REPO_ROOT / "README.md").exists()
    assert (REPO_ROOT / path).exists(), f"{name} cites a file that is not in the tree"


def test_healthz_checks_point_at_a_route_the_server_actually_serves():
    """Each python worker's ``/healthz`` default must be a real route.

    Read from the source rather than from the catalogue's own comment, so a
    renamed route fails here instead of silently answering 404 at the gate.
    """
    expected = {
        "digikey": "digikey/src/digikey/server.py",
        "digigraph": "digigraph/src/digigraph/server.py",
        "digisearch": "digisearch/src/digisearch/server.py",
        "digivault": "digivault/src/digivault/server.py",
        "digitrace": "digitrace/src/digitrace/server.py",
    }
    for name, path in expected.items():
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
        assert '"/healthz"' in text, f"{name} no longer serves /healthz"


def test_unconfigured_surfaces_are_skipped_not_guessed():
    """Anything I could not source from the tree must be env-configured."""
    unsourced = {
        "mcp-tools-list",
        "digitrace-ingest-roundtrip",
        "r2-put-get",
        "kv-put-get",
        "d1-put-get",
    }
    for check in contracts.BUILTIN_CHECKS:
        if check.name in unsourced:
            assert check.url is None, f"{check.name} has an unsourced default URL"
            assert check.requires, f"{check.name} has no env var to configure it with"


# --- profile selection -------------------------------------------------------


def test_profile_selection_keeps_all_and_the_named_profile():
    checks = contracts.BUILTIN_CHECKS
    core = contracts.select(checks, "core")
    everything = contracts.select(checks, "all")

    assert {c.name for c in core} <= {c.name for c in everything}
    assert len(everything) >= len(core)


def test_a_check_marked_all_is_in_every_profile():
    rows = (
        contracts.Check(
            name="x", kind="http", url="http://127.0.0.1:1/x", profiles=("all",), source="t"
        ),
        contracts.Check(
            name="y", kind="http", url="http://127.0.0.1:1/y", profiles=("core",), source="t"
        ),
    )
    assert {c.name for c in contracts.select(rows, "core")} == {"x", "y"}
    assert {c.name for c in contracts.select(rows, "chat")} == {"x"}


# --- contract overlay: feature-detected, never a third format ---------------


def test_absent_contract_yields_the_builtin_defaults(tmp_path):
    checks, origin = contracts.load_checks(tmp_path)
    assert origin == "built-in defaults"
    assert len(checks) == len(contracts.BUILTIN_CHECKS)


def test_a_contract_overlays_a_builtin_without_deleting_it(tmp_path):
    """A contract may retarget a named check; the plan's surfaces must survive.

    The plan names the surfaces, so a contract that lists one service cannot
    quietly remove the other twelve.
    """
    (tmp_path / "config" / "contract").mkdir(parents=True)
    (tmp_path / "config" / "contract" / "services.yaml").write_text(
        "services:\n"
        "  - name: digigraph\n"
        "    port: 9999\n"
        "    health_path: /healthz\n"
        "    profiles: [core]\n",
        encoding="utf-8",
    )
    checks, origin = contracts.load_checks(tmp_path)

    assert origin != "built-in defaults"
    assert len(checks) == len(contracts.BUILTIN_CHECKS)
    digigraph = next(c for c in checks if c.name == "digigraph")
    assert digigraph.url.endswith(":9999/healthz")
    assert next(c for c in checks if c.name == "digikey") is not None


def test_a_contract_may_add_a_check(tmp_path):
    (tmp_path / "config" / "contract").mkdir(parents=True)
    (tmp_path / "config" / "contract" / "contract.yaml").write_text(
        "- name: bespoke\n  url: http://127.0.0.1:7000/healthz\n  profiles: [core]\n",
        encoding="utf-8",
    )
    checks, _ = contracts.load_checks(tmp_path)
    assert "bespoke" in {c.name for c in checks}


# --- resolution: exactly one of url / skip reason ----------------------------


def test_resolve_returns_a_url_or_a_reason_never_both():
    for check in contracts.BUILTIN_CHECKS:
        url, reason = contracts.resolve(check, {})
        assert (url is None) != (reason is None), f"{check.name} resolved to both/neither"


def test_an_env_var_configures_an_unconfigured_check():
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "r2-put-get")
    assert check.url is None
    url, reason = contracts.resolve(check, {"DT_R2_URL": "http://127.0.0.1:8787/r2"})
    assert url == "http://127.0.0.1:8787/r2"
    assert reason is None


# --- preflight: a check that finds nothing must be able to find something ----


def test_preflight_passes_when_every_tool_is_present(tmp_path):
    report = preflight.run_preflight(
        path="/usr/bin:/bin",
        env={"DT_DISK_PATH": str(tmp_path)},
        tools=(preflight.ToolCheck("make", ("make",), "install make"),),
        disk_probe=lambda path: 50.0,
    )
    assert report.ok
    assert report.missing == ()


def test_preflight_fails_and_names_the_missing_tool(tmp_path):
    """The non-vacuity control: a gate that cannot fail proves nothing.

    Control on the same call: the disk probe returns a healthy 50 GiB and the
    tool check is the only thing that fails, so the verdict is attributable.
    """
    report = preflight.run_preflight(
        path="",
        env={"DT_DISK_PATH": str(tmp_path)},
        tools=(preflight.ToolCheck("docker", ("definitely-not-a-real-binary",), "start docker"),),
        disk_probe=lambda path: 50.0,
    )
    assert not report.ok
    assert report.missing == ("docker",)


def test_preflight_fails_on_low_disk_even_with_every_tool_present(tmp_path):
    report = preflight.run_preflight(
        path="/usr/bin:/bin",
        env={"DT_DISK_PATH": str(tmp_path)},
        tools=(preflight.ToolCheck("make", ("make",), "install make"),),
        disk_probe=lambda path: 1.0,
    )
    assert not report.ok
    assert report.missing == ("disk",)


def test_preflight_names_the_tool_it_could_not_find():
    """The missing-binary detail must carry the install hint, not just 'missing'."""
    report = preflight.run_preflight(
        path="",
        env={"DT_DISK_PATH": "/tmp"},
        tools=(
            preflight.ToolCheck(
                "docker", ("definitely-not-a-real-binary",), "start Docker Desktop"
            ),
        ),
        disk_probe=lambda path: 50.0,
    )
    detail = next(r.detail for r in report.results if r.name == "docker")
    assert "Docker Desktop" in detail


def test_preflight_uses_the_env_disk_override(tmp_path):
    """DT_DISK_PATH must actually reach the probe (macOS sealed-snapshot trap)."""
    seen = []

    def probe(path):
        seen.append(path)
        return 50.0

    preflight.run_preflight(
        path="/usr/bin:/bin",
        env={"DT_DISK_PATH": str(tmp_path)},
        tools=(),
        disk_probe=probe,
    )
    assert seen == [str(tmp_path)]


def test_wrangler_is_satisfied_by_npx_alone():
    """The wrangler entry ships as ``npx wrangler``: npx alone satisfies it."""
    report = preflight.check_tool(
        preflight.ToolCheck("wrangler", ("npx", "wrangler"), "h"), path="/usr/bin:/bin"
    )
    assert report.ok


# --- DIG-2959: a probe must address the HOST-published port -------------------
#
# compose republishes digichat as ${DIGICHAT_PUBLISH_PORT:-3005} -> 3000, so the
# container port and the host port differ. The gate used to probe the container
# port and reported a healthy, `Up (healthy)` container as "Connection refused".
# ollama has the same shape (11435 -> 11434) but is `url=None` + `requires`, so it
# skips instead of mis-probing: this guard covers the case that actually bites.


def _host_bind_port(host_bind: str) -> str | None:
    """The host port a service is published on, with ${VAR:-default} resolved."""
    resolved = contracts._expand_env(str(host_bind), {})
    match = re.search(r":(\d+)", resolved)
    return match.group(1) if match else None


def test_no_builtin_probe_uses_a_container_port_compose_republishes_elsewhere():
    """The load-bearing guard: host_bind, not container_port, is what a probe can reach."""
    doc = yaml.safe_load((REPO_ROOT / "config/contract/services.yaml").read_text())
    rows = {row["name"]: row for row in doc["services"]}

    violations = []
    checked = []
    for check in contracts.BUILTIN_CHECKS:
        row = rows.get(check.name)
        if row is None or check.url is None:
            continue
        host_bind, container_port = row.get("host_bind"), row.get("container_port")
        if host_bind is None or container_port is None or "null" in str(host_bind):
            continue
        host_port = _host_bind_port(host_bind)
        probe_port = re.search(r":(\d+)", contracts._expand_env(check.url, {}) or "")
        if not host_port or not probe_port:
            continue
        checked.append(check.name)
        if probe_port.group(1) != host_port:
            violations.append(
                f"{check.name} probes :{probe_port.group(1)} but compose publishes "
                f"{host_bind} (container_port {container_port})"
            )

    # The guard is worthless if it inspects nothing: digichat is the row it exists for.
    assert "digichat" in checked, f"digichat row not inspected; checked={checked}"
    assert not violations, violations


def test_digichat_probe_defaults_to_the_compose_published_port():
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digichat")
    url, reason = contracts.resolve(check, {})
    assert reason is None
    assert url == "http://127.0.0.1:3005/api/health"


def test_digichat_probe_follows_the_publish_port_override():
    """compose supports DIGICHAT_PUBLISH_PORT; the gate must follow it.

    The *host* is deliberately not templated: a 0.0.0.0 bind still answers on
    127.0.0.1, and the gate's default must stay provably loopback.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digichat")
    url, reason = contracts.resolve(check, {"DIGICHAT_PUBLISH_PORT": "3999"})
    assert reason is None
    assert url == "http://127.0.0.1:3999/api/health"
    # An empty override must not produce a bare ":" in the URL.
    assert contracts.resolve(check, {"DIGICHAT_PUBLISH_PORT": ""})[0] == (
        "http://127.0.0.1:3005/api/health"
    )


def test_env_expansion_falls_back_to_the_declared_default():
    check = contracts.Check(
        name="probe",
        kind="http",
        url="http://127.0.0.1:${DT_PROBE_PORT:-4321}/x",
        profiles=("core",),
        source="test",
    )
    assert contracts.resolve(check, {})[0] == "http://127.0.0.1:4321/x"
    # An empty value is not a value: it must take the default, not produce ":".
    assert contracts.resolve(check, {"DT_PROBE_PORT": ""})[0] == "http://127.0.0.1:4321/x"
    assert contracts.resolve(check, {"DT_PROBE_PORT": "5555"})[0] == "http://127.0.0.1:5555/x"


def test_a_configured_url_is_never_env_expanded():
    """A `requires` value is keyed on the exact path the caller supplied."""
    check = contracts.Check(
        name="r2-put-get",
        kind="http",
        url="http://127.0.0.1:1/",
        profiles=("core",),
        source="test",
        requires="DT_R2_URL",
    )
    url, _ = contracts.resolve(check, {"DT_R2_URL": "http://x/${FOO}"})
    assert url == "http://x/${FOO}"


def test_a_requires_url_gets_no_path_unless_the_check_opts_in():
    """The default stays "exactly as configured" (DIG-2959).

    resolve() must not append a probe path to a requires URL just because it
    looks like an origin: a local binding route is keyed on the path the
    caller supplied. Opting in is per-check and explicit.
    """
    check = contracts.Check(
        name="r2-put-get",
        kind="http",
        url=None,
        profiles=("core",),
        source="test",
        requires="DT_R2_URL",
    )
    url, reason = contracts.resolve(check, {"DT_R2_URL": "http://127.0.0.1:8787"})
    assert reason is None
    assert url == "http://127.0.0.1:8787"


def test_dashboard_api_probes_healthz_not_the_origin():
    """The gate must ask dashboard-api for /healthz, not the origin.

    apps/dashboard-api/src/index.ts routes only /healthz, /ledger,
    /v1/tables/* and the MCP path; every other GET answers
    errorResponse("bad_request", "unknown route ...") at :244/:255. Probing
    the origin alone therefore reads 400 from a healthy service.

    DIG-2697: the row no longer takes a requires= key. DT_DASHBOARD_API_URL
    had no producer anywhere in the repo, so the check resolved to
    (None, "not set") -- permanently SKIPPED, which health.py counts as a
    failure under REQUIRE_ALL=1. It now carries a literal loopback default
    in digichat/digitrace shape, so it resolves with nothing configured at
    all and DT_DASHBOARD_API_PORT overrides the port.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "dashboard-api")
    assert check.requires is None, "a requires key with no producer skips forever"
    assert check.path is None, "the probe path now lives in the built-in URL"

    # Nothing configured: the built-in default must resolve, never skip.
    url, reason = contracts.resolve(check, {})
    assert reason is None
    assert url == "http://127.0.0.1:8887/healthz"
    assert url.endswith("/healthz"), "probe the route, not the origin"

    # Env-overridable, same shape as digichat's port template.
    url, reason = contracts.resolve(check, {"DT_DASHBOARD_API_PORT": "9999"})
    assert reason is None
    assert url == "http://127.0.0.1:9999/healthz"

    # An empty value falls back to the default rather than to a bare port.
    url, reason = contracts.resolve(check, {"DT_DASHBOARD_API_PORT": ""})
    assert reason is None
    assert url == "http://127.0.0.1:8887/healthz"


def test_with_path_does_not_double_an_already_complete_path():
    """An operator who exports the full probe URL gets the same URL back."""
    base = "http://127.0.0.1:8788/healthz"
    assert contracts._with_path(base, "/healthz") == base


def test_with_path_keeps_query_and_fragment():
    base = "http://127.0.0.1:8788/prefix?a=1#f"
    got = contracts._with_path(base, "/healthz")
    assert got == "http://127.0.0.1:8788/prefix/healthz?a=1#f"
