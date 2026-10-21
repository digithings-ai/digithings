"""Catalogue and preflight tests for the local self-host stack (DIG-2775, S7).

Two properties matter here. Every built-in default URL must trace to a source
in the tree, so a check cannot silently point at a port nothing serves; and a
preflight that finds nothing wrong must be proven able to find something.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

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


def test_the_digigraph_probe_defaults_to_the_compose_published_port():
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    url, reason = contracts.resolve(check, {})
    assert reason is None
    assert url == "http://127.0.0.1:8000/healthz"


def test_the_digigraph_probe_follows_the_port_override():
    """A host where 8000 belongs to another stack needs the real port.

    Measured on this host: 8000 answered 204 (a woodpecker server from another
    stack) while the digigraph on 18000 answered 200, so the gate called a
    healthy digigraph FAIL.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    url, reason = contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "18000"})
    assert reason is None
    assert url == "http://127.0.0.1:18000/healthz"
    # An empty value is not a value: it must take the default, not produce ":".
    assert contracts.resolve(check, {"DT_DIGIGRAPH_PORT": ""})[0] == (
        "http://127.0.0.1:8000/healthz"
    )


def test_the_digigraph_probe_never_leaves_loopback():
    """The knob moves the port; it never points the gate off the machine."""
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    assert check.url.startswith("http://127.0.0.1:")
    assert "DIGIGRAPH_HOST" not in check.url
    # The resolved URL is the one the probe actually opens, so the invariant
    # has to hold there and not only in the template.
    resolved = contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "18000"})[0]
    assert urlsplit(resolved).hostname == "127.0.0.1"
    # The mutant that breaks the invariant: '8000@evil.com' is a legal userinfo
    # string, so urlsplit reads the host as 'evil.com'. There is no URL at all
    # for it, so there is nothing that can leave loopback.
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "8000@evil.com"})


def test_the_digigraph_probe_follows_the_port_override_in_the_merged_catalogue():
    """The knob has to survive the contract merge, not only the built-ins.

    The gate runs the merged catalogue, and the merge takes the contract row
    over the built-in one (``url=override.url or builtin.url``). A contract
    row that grew a ``port`` key would silently drop the knob, so the merged
    catalogue is what the test reads.
    """
    checks, _origin = contracts.load_checks(REPO_ROOT)
    check = next(c for c in checks if c.name == "digigraph")
    url, reason = contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "18000"})
    assert reason is None
    assert url == "http://127.0.0.1:18000/healthz"


# --- the digigraph port knob is a port, or it is refused (DIG-4911) ---------
#
# A value that is not a port does not make the templated URL unparseable: it
# makes the URL point somewhere else. "8000@evil.com" expands to
# "http://127.0.0.1:8000@evil.com/healthz", which parses, with "127.0.0.1:8000"
# read as userinfo and the host read as "evil.com". So the value is validated
# before it is templated, and a value that is not a port is refused.


def _digigraph_check():
    return next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")


@pytest.mark.parametrize(
    "value",
    [
        "8000@evil.com",
        "8000/@evil.com",
        "8000#x",
        "0",
        "65536",
        "-1",
        "+8000",
        " 8000",
        "８０００",
        "0x1F40",
    ],
)
def test_the_digigraph_probe_refuses_a_value_that_is_not_a_port(value):
    """Each of these is a value a raw expansion would have templated.

    Surrounding whitespace is in the list: a port is plain decimal digits
    (DIG-4911 ask 1), so " 8000" is refused and never trimmed into a port.
    The Supabase pair keeps its own soft policy, because localstack.localenv
    normalizes DT_SUPABASE_PORT before the contracts see it.
    """
    check = _digigraph_check()
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": value})
    message = str(excinfo.value)
    # The operator has to learn which knob is wrong.
    assert "DT_DIGIGRAPH_PORT" in message
    # ... and that the value they exported is the one that is wrong.
    assert value in message


def test_the_refusal_is_a_refusal_and_not_a_fall_back_to_the_default():
    """A refused knob must not become the default port behind the operator's back."""
    check = _digigraph_check()
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "8000@evil.com"})
    # The default is still what an unset knob gives - the refusal is about the
    # value, not about the port the default happens to be.
    assert contracts.resolve(check, {})[0] == "http://127.0.0.1:8000/healthz"


def test_a_refusal_names_the_reason_and_the_range():
    check = _digigraph_check()
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "65536"})
    message = str(excinfo.value)
    assert "DT_DIGIGRAPH_PORT" in message
    assert "65536" in message
    assert "1-65535" in message


def test_a_refusal_says_what_a_port_looks_like():
    check = _digigraph_check()
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "8000@evil.com"})
    assert "decimal digits" in str(excinfo.value)


@pytest.mark.parametrize("value", ["1", "18000", "65535"])
def test_the_digigraph_probe_accepts_a_plain_port(value):
    check = _digigraph_check()
    url, reason = contracts.resolve(check, {"DT_DIGIGRAPH_PORT": value})
    assert reason is None
    assert url == f"http://127.0.0.1:{value}/healthz"
    split = urlsplit(url)
    assert split.hostname == "127.0.0.1"
    assert split.port == int(value)


@pytest.mark.parametrize("config", [{}, {"DT_DIGIGRAPH_PORT": ""}])
def test_the_digigraph_probe_keeps_the_default_when_the_knob_is_unset_or_empty(config):
    check = _digigraph_check()
    url, reason = contracts.resolve(check, config)
    assert reason is None
    assert url == "http://127.0.0.1:8000/healthz"
    assert urlsplit(url).hostname == "127.0.0.1"


def test_the_resolved_url_is_refused_unless_it_is_loopback_on_that_port():
    """The guard is on the URL the probe opens, not only on the value's shape.

    A template that named a host other than 127.0.0.1 would carry a perfectly
    valid port, so the digit check alone would let it through. The resolved
    URL is parsed and refused unless it is the loopback probe on the port
    that was validated.
    """
    off_machine = contracts.Check(
        name="digigraph",
        kind="http",
        url="http://example.com:${DT_DIGIGRAPH_PORT:-8000}/healthz",
        profiles=("core",),
        source="test",
    )
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(off_machine, {"DT_DIGIGRAPH_PORT": "8000"})
    message = str(excinfo.value)
    assert "127.0.0.1" in message
    # The needle is a parsed value, not a string literal, so the CodeQL rule
    # py/incomplete-url-substring-sanitization does not read this as a check
    # on a URL substring (the alert it raised on the previous head). The line
    # stays: it is the only pin on "the refusal names the offending host".
    assert urlsplit(off_machine.url).hostname in message


def test_the_raw_expansion_would_have_pointed_off_the_machine():
    """The control: what the code did before the refusal, and why it mattered.

    Without the validation the raw value is templated into the URL and the
    result parses - with the host reading "evil.com" and "127.0.0.1:8000"
    read as userinfo. The probe would have left the machine.
    """
    naive = "http://127.0.0.1:8000@evil.com/healthz"
    split = urlsplit(naive)
    assert split.hostname == "evil.com"
    assert split.username == "127.0.0.1"
    # And the value the gate now refuses is exactly that one.
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(_digigraph_check(), {"DT_DIGIGRAPH_PORT": "8000@evil.com"})


def test_every_port_knob_is_validated_and_guarded():
    """The rule is not a list of knobs: it is the port slot of the URL.

    Every built-in row that templates a knob has to refuse a value that is
    not a port, and the URL it resolves to has to be the loopback probe on
    the port the knob was validated to carry. There is no strict-knob list to
    keep in sync, so a new templated row is guarded the moment it lands.
    """
    templated = [c for c in contracts.BUILTIN_CHECKS if c.url and "${" in c.url]
    assert templated, "the catalogue templates knobs; the guard has to cover them"
    for check in templated:
        knob = re.search(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", check.url).group(1)
        with pytest.raises(contracts.InvalidPort):
            contracts.resolve(check, {knob: "8000@evil.com"})
        url = contracts.resolve(check, {knob: "18000"})[0]
        assert urlsplit(url).hostname == "127.0.0.1"
        assert urlsplit(url).port == 18000


def test_the_refusal_covers_the_port_as_well_as_the_host():
    """The guard checks the port too, not only the host.

    Deleting the port half of the comparison leaves the host half to catch
    the off-machine case, so the suite would stay green on a guard that
    accepts a URL on the loopback but on the wrong port.
    """
    with pytest.raises(contracts.InvalidPort):
        contracts._assert_loopback_port(
            "http://127.0.0.1:9999/healthz", "DT_DIGIGRAPH_PORT", 8000
        )


def test_a_knob_outside_the_port_slot_keeps_the_plain_expansion():
    """The port slot decides, not a knob list.

    A reference that does not stand for the port keeps the plain expansion,
    so this change does not alter how a non-port templated default behaves.
    """
    other = contracts.Check(
        name="probe",
        kind="http",
        url="http://127.0.0.1:8000/${DT_OTHER_PATH:-api}/x",
        profiles=("core",),
        source="test",
    )
    assert contracts.resolve(other, {"DT_OTHER_PATH": "api"})[0] == (
        "http://127.0.0.1:8000/api/x"
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


def test_the_supabase_probes_follow_the_local_port_knob():
    """The gate has to address the Supabase set the local stack starts.

    core-local holds 54321, so probing that port would read core-local's
    database and report a false PASS (DIG-4501). Only the port is templated:
    the host stays on the loopback, like every other builtin.
    """
    for name, path in (("supabase-rest", "/rest/v1/"), ("supabase-auth", "/auth/v1/health")):
        check = next(c for c in contracts.BUILTIN_CHECKS if c.name == name)
        url, reason = contracts.resolve(check, {"DT_SUPABASE_PORT": "55421"})
        assert reason is None
        assert url == f"http://127.0.0.1:55421{path}"
        # without the knob the local stack's own default stands
        url, reason = contracts.resolve(check, {})
        assert url == f"http://127.0.0.1:{contracts.DEFAULT_API_PORT}{path}"
        assert url.startswith("http://127.0.0.1:")


# --- DIG-4905: a port knob carries a port, or the gate refuses it -----------
#
# The knob value is substituted into the port slot of a loopback URL and the
# gate then opens that URL. A value that is not a port is therefore the one
# thing that can move the probe off this machine: '8000@evil.com' is a legal
# userinfo string, and urlsplit("http://127.0.0.1:8000@evil.com/healthz")
# reports hostname 'evil.com'.

#: Every builtin row whose URL carries a port knob, and the knob that carries
#: it. The list is closed on purpose: a new templated row cannot be added
#: without a guard for it (test_every_knob_row_is_guarded).
PORT_KNOBS: tuple[tuple[str, str], ...] = (
    ("supabase-rest", "DT_SUPABASE_PORT"),
    ("supabase-auth", "DT_SUPABASE_PORT"),
    ("digigraph", "DT_DIGIGRAPH_PORT"),
    ("digichat", "DIGICHAT_PUBLISH_PORT"),
    ("dashboard-api", "DT_DASHBOARD_API_PORT"),
)

#: Values that are not ports. The first one is the mutant that turns the
#: probe into a request to another host; the rest are the shapes a number
#: can take that a port cannot.
NOT_A_PORT: tuple[str, ...] = (
    "8000@evil.com",
    "evil.com",
    "8000/../evil.com",
    "0",
    "65536",
    "+8000",
    "8_000",
    "not-a-port",
    "8000 evil",
    "٨٠٠٠",  # Arabic-Indic digits: int() reads them, a port may not carry them
)


@pytest.mark.parametrize(("name", "knob"), PORT_KNOBS)
@pytest.mark.parametrize("value", NOT_A_PORT)
def test_a_port_knob_that_is_not_a_port_is_refused(name, knob, value):
    """A knob value that is not a port never becomes a URL.

    The refusal is loud and it names the knob, so the operator sees which
    variable to fix instead of a probe that quietly went somewhere else.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == name)
    with pytest.raises(contracts.InvalidPort) as caught:
        contracts.resolve(check, {knob: value})
    assert knob in str(caught.value)


@pytest.mark.parametrize(("name", "knob"), PORT_KNOBS)
def test_no_port_knob_value_can_produce_an_off_machine_url(name, knob):
    """The property, stated on the URL the gate opens.

    Either the value is refused, or the URL it produces still addresses the
    loopback host. There is no third outcome.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == name)
    for value in (*NOT_A_PORT, "8000", "1", "65535"):
        try:
            url = contracts.resolve(check, {knob: value})[0]
        except contracts.InvalidPort:
            continue
        assert urlsplit(url).hostname in ("127.0.0.1", "localhost"), url
        assert urlsplit(url).username is None, url


def test_every_knob_row_is_guarded():
    """A knob nobody names is a knob nobody guards."""
    templated = {c.name for c in contracts.BUILTIN_CHECKS if c.url and "${" in c.url}
    assert templated == {name for name, _ in PORT_KNOBS}


def test_a_port_knob_with_surrounding_whitespace_is_refused():
    """Whitespace around a port is not a port.

    DIG-4911 ask 1: the port is plain decimal digits, so " 18000 " is not one
    and is refused like any other value that is not a port. The Supabase pair
    keeps its own soft policy, because localstack.localenv normalizes
    DT_SUPABASE_PORT before the contracts see it.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(check, {"DT_DIGIGRAPH_PORT": " 18000 "})
    assert "DT_DIGIGRAPH_PORT" in str(excinfo.value)


def test_the_dashboard_api_probe_never_leaves_loopback():
    """The row that shipped with the same hole, guarded the same way."""
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "dashboard-api")
    resolved = contracts.resolve(check, {"DT_DASHBOARD_API_PORT": "9999"})[0]
    assert urlsplit(resolved).hostname == "127.0.0.1"
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(check, {"DT_DASHBOARD_API_PORT": "8000@evil.com"})


# --- a contract row's port is a port, or the row is refused (DIG-4905) -----
#
# A contract row can carry a `port:` key, and the catalogue turns it into the
# loopback URL of that row. The port used to be read with a bare int(): "8_000"
# and "+8000" were coerced into a number, and "8000@evil.com" raised a bare
# ValueError that reached `dt status` as a traceback. The port is read with
# the same validator the knobs use, so the module holds one idea of what a
# port is. A row that carries anything else is refused: the row stays in the
# catalogue with the reason on it, so the merge cannot fall back to the
# built-in URL and the gate fails the row.


def _contract(tmp_path: Path, body: str) -> None:
    """Write a contract file into a root the catalogue reader accepts."""
    (tmp_path / "config" / "contract").mkdir(parents=True)
    (tmp_path / "config" / "contract" / "services.yaml").write_text(body, encoding="utf-8")


def _digigraph_row(tmp_path: Path) -> contracts.Check:
    checks, _origin = contracts.load_checks(tmp_path)
    return next(c for c in checks if c.name == "digigraph")


@pytest.mark.parametrize("value", [*NOT_A_PORT, " 8000 "])
def test_a_contract_row_with_a_port_that_is_not_a_port_is_refused(tmp_path, value):
    """The contract port is read with the same rule as the knobs.

    "8_000" and "+8000" were the two shapes int() read as numbers, and
    "8000@evil.com" was the one that raised. None of them is a port, and a
    port carries no whitespace either.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        f"    port: {value!r}\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.InvalidPort) as caught:
        contracts.resolve(row, {})
    message = str(caught.value)
    # The operator has to learn which row is wrong ...
    assert "digigraph" in message
    # ... and which value they wrote.
    assert value in message


def test_a_refused_contract_row_does_not_fall_back_to_the_built_in_url(tmp_path):
    """A refusal is not a quiet fallback to the default port.

    The merge takes the contract row over the built-in one, so a row that
    carries a refused port must not leave the built-in URL standing: the
    operator asked for a port that is not a port, and the gate has to say so
    instead of probing something else.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: '8000@evil.com'\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.url is None, "a refused row must not carry a URL"
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(row, {})


def test_reading_a_contract_with_a_bad_port_does_not_raise(tmp_path):
    """`dt status` reads the catalogue before it probes anything.

    The bare ValueError out of the old int() reached `dt status` as a
    traceback. The refusal travels on the row instead, so reading the
    catalogue never raises.
    """
    _contract(
        tmp_path,
        "services:\n  - name: digigraph\n    port: '8000@evil.com'\n",
    )
    checks, origin = contracts.load_checks(tmp_path)
    assert origin != "built-in defaults"
    assert [c.name for c in checks if c.refusal] == ["digigraph"]


@pytest.mark.parametrize("port", [1, 8000, 9999, 65535])
def test_a_contract_row_with_a_valid_port_still_composes_the_loopback_url(
    tmp_path, port
):
    """The rule refuses the values that are not ports, not the ports."""
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        f"    port: {port}\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    assert row.url == f"http://127.0.0.1:{port}/healthz"
    assert urlsplit(row.url).hostname == "127.0.0.1"
    assert urlsplit(row.url).port == port


@pytest.mark.parametrize("yaml_port", ["8000.0", "true"])
def test_a_contract_port_that_is_not_an_integer_is_refused(tmp_path, yaml_port):
    """The port arrives from YAML, so it can be a float or a bool first.

    ``port: 8000.0`` is a number and not a port, and ``port: true`` is not a
    number at all. Neither is coerced into one.
    """
    _contract(
        tmp_path,
        f"services:\n  - name: digigraph\n    port: {yaml_port}\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.InvalidPort):
        contracts.resolve(row, {})


def test_a_contract_row_without_a_port_keeps_the_built_in_url(tmp_path):
    """A row that carries no port is not a refusal (unchanged behaviour).

    The contract we ship lists its services with a container_port and no
    health port, so those rows fall back to the built-in URL as they always
    did -- the digigraph row keeps its DT_DIGIGRAPH_PORT knob.
    """
    _contract(
        tmp_path,
        "services:\n  - name: digigraph\n    profile: core\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    assert row.url == "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz"


def test_the_shipped_contract_carries_no_refusal():
    """The contract we ship must not trip the rule it introduced."""
    checks, origin = contracts.load_checks(REPO_ROOT)
    assert origin != "built-in defaults"
    assert [c.name for c in checks if c.refusal] == []
    digigraph = next(c for c in checks if c.name == "digigraph")
    assert digigraph.url == "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz"
