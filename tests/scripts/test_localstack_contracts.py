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
    The Supabase pair keeps its own soft policy, because
    localstack.supabase_ports accepts only an ASCII-digit port and
    localstack.localenv.apply_defaults writes the resolved port back into
    the environment before any handler runs.
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


def test_the_port_that_lands_in_the_url_is_the_integer_it_validates_to():
    """The URL carries the port, not the text of the value.

    The knob is validated and the validated integer is what lands in the URL
    slot, so a value written with a leading zero cannot leave a padded port
    in the URL the gate opens. Deleting the substitution (templating the raw
    value instead) changes the URL text and nothing else, which is exactly
    why the text has to be pinned here.
    """
    check = _digigraph_check()
    url, reason = contracts.resolve(check, {"DT_DIGIGRAPH_PORT": "00800"})
    assert reason is None
    assert url == "http://127.0.0.1:800/healthz"
    assert urlsplit(url).port == 800


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("00800", "http://127.0.0.1:800/healthz"),
        ("08000", "http://127.0.0.1:8000/healthz"),
        ("00001", "http://127.0.0.1:1/healthz"),
        ("18000", "http://127.0.0.1:18000/healthz"),
    ],
)
def test_the_validated_integer_and_not_the_raw_text_lands_in_the_url(value, expected):
    """What lands in the port slot is ``str(port)``, not the value as written.

    A leading-zero value is a port (same integer), but the URL carries the
    canonical integer, so the probe opens exactly the port that was validated.
    Substituting the raw text instead (``:00800``) turns this red.
    """
    url, reason = contracts.resolve(_digigraph_check(), {"DT_DIGIGRAPH_PORT": value})
    assert reason is None
    assert url == expected


@pytest.mark.parametrize(
    "template",
    [
        "http://${DT_PROBE_HOST:-127.0.0.1}:8000/x",
        "http://${DT_PROBE_HOST:-127.0.0.1}:${DT_PROBE_PORT:-8000}/x",
        "http://${DT_PROBE_USER:-u}@127.0.0.1:${DT_PROBE_PORT:-8000}/x",
        "http://127.0.0.1${DT_PROBE_SUFFIX:-}:8000/x",
    ],
)
def test_a_reference_outside_the_port_slot_of_the_authority_is_refused(template):
    """Only the port of a probe URL may be templated.

    A reference in the host or userinfo is refused before any value lands,
    even when its value (or default) is the loopback: the template itself is
    the shape that could move the probe off the machine.
    """
    check = contracts.Check(
        name="probe", kind="http", url=template, profiles=("core",), source="test"
    )
    with pytest.raises(contracts.InvalidPort) as excinfo:
        contracts.resolve(check, {})
    assert "outside the port slot" in str(excinfo.value)


def test_a_url_with_only_a_path_reference_is_still_held_to_the_loopback():
    """The loopback check runs even when no reference filled the port slot."""
    off_machine = contracts.Check(
        name="probe",
        kind="http",
        url="http://example.com:8000/${DT_OTHER_PATH:-api}/x",
        profiles=("core",),
        source="test",
    )
    with pytest.raises(contracts.ContractRefusal) as excinfo:
        contracts.resolve(off_machine, {})
    assert "127.0.0.1" in str(excinfo.value)


@pytest.mark.parametrize(
    "url", ["http://u@127.0.0.1:8000/x", "http://u:p@127.0.0.1:8000/x", "http://:@127.0.0.1:8000/x"]
)
def test_userinfo_on_the_loopback_is_refused(url):
    """``user@127.0.0.1`` is the loopback, but no probe URL may carry userinfo."""
    with pytest.raises(contracts.ContractRefusal):
        contracts._assert_loopback_url(url, "probe")
    with pytest.raises(contracts.InvalidPort):
        contracts._assert_loopback_port(url, "DT_X", 8000)


def test_a_contract_url_with_userinfo_is_refused_through_resolve():
    """The userinfo refusal holds on the URL the gate opens, not only the helper."""
    check = contracts.Check(
        name="probe",
        kind="http",
        url="http://u@127.0.0.1:8000/healthz",
        profiles=("core",),
        source="test",
    )
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(check, {})


def test_every_builtin_template_still_resolves_on_its_defaults():
    """The stricter guard keeps every shipped template passing."""
    templated = [c for c in contracts.BUILTIN_CHECKS if c.url and "${" in c.url]
    assert templated
    for check in templated:
        url, reason = contracts.resolve(check, {})
        assert reason is None
        assert urlsplit(url).hostname == "127.0.0.1"


def test_a_padded_value_outside_the_port_slot_is_trimmed_and_not_refused():
    """The strip outside the port slot is pinned by the padded value.

    A reference that does not stand for the port is an ordinary value, so its
    surrounding whitespace is noise and is trimmed. An unpadded value cannot
    tell the trim from its absence, so the padded one is the case that holds
    the branch in place: dropping the trim leaves the padding in the URL.
    """
    other = contracts.Check(
        name="probe",
        kind="http",
        url="http://127.0.0.1:8000/${DT_OTHER_PATH:-api}/x",
        profiles=("core",),
        source="test",
    )
    assert contracts.resolve(other, {"DT_OTHER_PATH": " api "})[0] == (
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
    with pytest.raises(contracts.ContractRefusal) as caught:
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
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})
    # The source is the contract row's own, so the table points at the file
    # the operator has to fix and not at the built-in default.
    assert row.source == "config contract row 'digigraph'"


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
    with pytest.raises(contracts.ContractRefusal):
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
    assert origin == "config/contract/services.yaml"
    assert [c.name for c in checks if c.refusal] == []
    digigraph = next(c for c in checks if c.name == "digigraph")
    assert digigraph.url == "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz"


# --- the contract is read as the text that was written (DIG-4911) -----------
#
# YAML 1.1 reads `8_000` as 8000, `+8000` as 8000 and `017` as 15 (octal). A
# validator that only ever sees the coerced number cannot refuse the shapes
# the rule exists for: they arrive already turned into a port. The loader
# keeps a plain scalar as the text the operator wrote, so the port is what
# the file says.


@pytest.mark.parametrize("port", ["8_000", "+8000", "0x1f90", "1_0", "017"])
def test_a_contract_port_written_without_quotes_is_refused(tmp_path, port):
    """The port is read as it was written, not as YAML reads it.

    ``yaml.safe_load`` applies YAML 1.1 implicit typing, so ``8_000``,
    ``+8000`` and ``017`` never reach the validator as the text the operator
    wrote -- they arrive as 8000, 8000 and 15, and the rule cannot refuse
    what it never sees.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        f"    port: {port}\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert port in str(caught.value)


def test_a_contract_port_written_without_quotes_is_still_a_port(tmp_path):
    """The rule refuses the values that are not ports, not the ports.

    ``port: 8000`` is what an operator writes; it has to work.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: 8000\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    assert row.url == "http://127.0.0.1:8000/healthz"


@pytest.mark.parametrize("port", ["017", "08000", "0008000"])
def test_a_contract_port_has_to_be_spelled_the_way_it_is_read(tmp_path, port):
    """``017`` is 17 here and 15 to a reader that applies octal.

    A file that means two numbers is a file nobody can reason about, so the
    port has to be written the way it will be read: plain decimal digits.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        f"    port: {port}\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert port in str(caught.value)


def test_a_row_with_a_url_and_a_bad_port_is_refused(tmp_path):
    """A url does not hide a port that is not a port."""
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    url: http://127.0.0.1:9000/healthz\n"
        "    port: '8000@evil.com'\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert "8000@evil.com" in str(caught.value)


def test_a_row_with_a_url_and_a_port_uses_the_url(tmp_path):
    """The url wins when both are there and both are good.

    Pinned, so the precedence is a decision and not an accident.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    url: http://127.0.0.1:9000/healthz\n"
        "    port: 8000\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    assert row.url == "http://127.0.0.1:9000/healthz"


@pytest.mark.parametrize("url", ["12345", "{}", "[]"])
def test_a_row_whose_url_is_not_a_string_is_refused(tmp_path, url):
    """A malformed url is refused, not replaced by the built-in one.

    The fallback left the gate probing the built-in URL, so a typo in the
    contract was invisible: the row looked configured and probed something
    the operator never wrote.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        f"    url: {url}\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.url is None, "a refused row must not carry a URL"
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_a_row_whose_url_leaves_the_machine_is_refused(tmp_path):
    """A contract row may not point the probe off this machine.

    Only the composed URLs used to be checked, so a row that carried a
    literal url was trusted verbatim.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    url: http://10.0.0.5:8080/healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert "127.0.0.1" in str(caught.value)


def test_a_row_whose_requires_is_not_a_name_is_refused(tmp_path):
    """A malformed requires used to crash the gate with a TypeError.

    ``config.get(<a list>)`` raises, and the gate caught only the port
    refusal, so the traceback reached the terminal.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    requires:\n"
        "      - DT_DIGIGRAPH_URL\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert "requires" in str(caught.value)


def test_a_row_whose_health_path_is_not_a_string_is_refused(tmp_path):
    """A malformed health_path is refused, not ignored.

    Ignored, it would compose the built-in default path and the row would
    probe a route the operator never named.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: 8000\n"
        "    health_path: {}\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert "health_path" in str(caught.value)


def test_the_resolved_url_is_refused_unless_it_is_on_the_loopback():
    """Defence in depth: the URL the probe opens has to be the loopback one.

    A row that carries a url off the machine is refused when the catalogue
    reads it, and again here -- so a row that reaches the gate another way
    still cannot move the probe off this machine.
    """
    row = contracts.Check(
        name="rogue",
        kind="http",
        url="http://10.0.0.5:8080/healthz",
        profiles=("all",),
        source="test fixture",
    )
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    assert "127.0.0.1" in str(caught.value)


def test_a_row_that_names_a_configuration_variable_with_a_list_is_refused():
    """Belt and braces: a row whose requires is not a name is refused.

    The catalogue refuses it when it reads the contract; this is the same
    rule at the point where the lookup happens, so the row cannot crash the
    lookup with a TypeError.
    """
    row = contracts.Check(
        name="rogue",
        kind="http",
        url=None,
        profiles=("all",),
        source="test fixture",
        requires=["DT_MCP_URL"],
    )
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_a_refused_row_is_in_every_profile(tmp_path):
    """A refusal that no profile selects is a refusal nobody sees.

    The contract the repo ships uses an empty profile list, and a refused
    row that landed in no profile would silently stop the built-in probe it
    shadows.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: '8000@evil.com'\n"
        "    profiles: []\n",
    )
    checks, _origin = contracts.load_checks(tmp_path)
    row = next(c for c in checks if c.name == "digigraph")
    assert row.refusal is not None
    for profile in ("core", "quant", "chat", "trace"):
        assert row.in_profile(profile), profile


def test_a_refused_row_shadows_the_requires_branch(tmp_path):
    """The refusal comes before the configuration branch.

    ``mcp-tools-list`` needs a configuration variable, so a refused row that
    shadowed it would skip if the refusal were raised after the requires
    branch -- and a skip reads as "not verified".
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: mcp-tools-list\n"
        "    port: '8000@evil.com'\n",
    )
    checks, _origin = contracts.load_checks(tmp_path)
    row = next(c for c in checks if c.name == "mcp-tools-list")
    assert row.refusal is not None
    # No DT_MCP_URL in the config: the refusal is what has to be raised.
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_a_row_we_cannot_name_is_kept_when_it_is_refused(tmp_path):
    """Dropping an unnamed row would drop the misconfiguration with it.

    The row is kept under a synthetic name so the gate fails it.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - port: '8000@evil.com'\n",
    )
    checks, origin = contracts.load_checks(tmp_path)
    refused = [c for c in checks if c.refusal]
    assert [c.name for c in refused] == ["contract row 0"]
    assert origin == "config/contract/services.yaml"


def test_a_contract_row_composes_the_health_path_it_carries(tmp_path):
    """The path is the row's own, not the built-in default."""
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: 9000\n"
        "    health_path: /livez\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.url == "http://127.0.0.1:9000/livez"


def test_the_origin_names_the_contract_file(tmp_path):
    """The origin is the file, so a gate run can say what it read."""
    _contract(tmp_path, "services:\n  - name: digigraph\n    profile: core\n")
    _checks, origin = contracts.load_checks(tmp_path)
    assert origin == "config/contract/services.yaml"


def test_the_source_follows_the_url_it_names(tmp_path):
    """A URL the contract carries is sourced from the contract.

    The built-in source describes the built-in URL, so a row that carries
    its own url and keeps the built-in's source points the reader at the
    wrong file.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    port: 9000\n"
        "    health_path: /healthz\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.url == "http://127.0.0.1:9000/healthz"
    assert row.source == "config contract row 'digigraph'"


def test_a_row_without_a_url_keeps_the_built_in_source(tmp_path):
    """A row that carries no url leaves the built-in's URL and its source.

    The contract we ship lists its services with a container port and no
    health url, so those rows keep the built-in URL -- and the source that
    describes it.
    """
    _contract(tmp_path, "services:\n  - name: digigraph\n    profile: core\n")
    row = _digigraph_row(tmp_path)
    assert row.url == "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz"
    assert "digigraph/src/digigraph/server.py" in row.source


def test_the_origin_names_a_contract_that_yields_no_readable_row(tmp_path):
    """A contract the reader cannot read is still the origin.

    Reading "built-in defaults" would hide the fact that the operator's
    contract was there and was ignored.
    """
    _contract(tmp_path, "services: []\n")
    checks, origin = contracts.load_checks(tmp_path)
    assert origin == "config/contract/services.yaml"
    # The built-ins still answer: the catalogue falls back, and says so.
    assert [c.name for c in checks] == [c.name for c in contracts.BUILTIN_CHECKS]


def test_a_refused_row_carries_its_reason_in_the_serialised_row(tmp_path):
    """The reason travels with the row, in the payload CI reads."""
    _contract(
        tmp_path,
        "services:\n  - name: digigraph\n    port: '8000@evil.com'\n",
    )
    row = _digigraph_row(tmp_path)
    payload = row.to_dict()
    assert payload["refusal"] is not None
    assert "8000@evil.com" in payload["refusal"]


def test_a_composed_url_that_leaves_the_loopback_is_refused():
    """The composed URL is checked, not only the port that went into it.

    The host is a constant in the shipped paths, so the check is only
    reachable by calling the composer with another host -- which is exactly
    what a future change would do.
    """
    with pytest.raises(contracts.InvalidPort):
        contracts._compose_url(8000, "/healthz", host="0.0.0.0")


def test_a_contract_that_is_neither_yaml_nor_json_is_a_named_error(tmp_path):
    """A broken contract file must not reach the CLI as a traceback."""
    (tmp_path / "config" / "contract").mkdir(parents=True)
    (tmp_path / "config" / "contract" / "services.yaml").write_text(
        "services: [\n  - name: digigraph\n", encoding="utf-8"
    )
    with pytest.raises(contracts.ContractParseError) as caught:
        contracts.load_checks(tmp_path)
    assert "services.yaml" in str(caught.value)


def test_a_contract_url_that_does_not_parse_is_refused_and_not_raised(tmp_path):
    """A URL that does not parse is a failed row, never a traceback.

    `urlsplit` raises ValueError on an authority with an unbalanced bracket
    ("Invalid IPv6 URL"). The parse happened outside the guard's try, so the
    error was not a refusal: it left the catalogue reader, the loader and
    the CLI, and `dt status` died with a stack trace before a single row was
    probed. The base did not crash there -- the row failed cleanly at probe
    time -- so this was a regression, and it broke this PR's own promise
    that a malformed row never reaches the terminal as a traceback.
    """
    _contract(
        tmp_path,
        "services:\n  - name: digigraph\n    url: 'http://[::1'\n",
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is not None
    assert "http://[::1" in row.refusal
    assert "127.0.0.1" in row.refusal
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_the_loopback_url_check_refuses_a_url_that_does_not_parse():
    """The guard holds the parse, so a broken URL is a refusal."""
    with pytest.raises(contracts.ContractRefusal):
        contracts._assert_loopback_url("http://[::1", "the URL of 'digigraph'")


def test_the_loopback_port_check_refuses_a_url_that_does_not_parse():
    """The port guard has the same shape and holds the parse as well."""
    with pytest.raises(contracts.InvalidPort):
        contracts._assert_loopback_port("http://[::1", "DT_DIGIGRAPH_PORT", 8000)


@pytest.mark.parametrize(
    ("url", "why"),
    [
        ("ftp://127.0.0.1:8000/x", "the scheme is not http"),
        ("http://127.0.0.1:99999/healthz", "the port is out of range"),
        ("http://127.0.0.1/healthz", "the URL carries no port"),
    ],
)
def test_a_contract_url_that_is_not_an_http_probe_is_refused(tmp_path, url, why):
    """On the loopback is not the same as a probe.

    `ftp://127.0.0.1/x` is on the loopback and still is not a probe: the
    gate opened a connection to the FTP default port. A port that is not a
    number in 1-65535 is not a port either. The host check alone let both
    through, and the PR body claimed more than the code did.
    """
    _contract(
        tmp_path,
        "services:\n  - name: digigraph\n    url: {!r}\n".format(url),
    )
    row = _digigraph_row(tmp_path)
    assert row.refusal is not None, why
    assert row.url is None
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("services:\n  - name: digigraph\n    port: ~\n", "a null port"),
        ("services:\n  - name: digigraph\n    url: ~\n", "a null url"),
        ("services:\n  - name: digigraph\n    url: ''\n", "an empty url"),
    ],
)
def test_a_contract_row_that_says_nothing_is_refused_and_not_read_as_absent(
    tmp_path, body, why
):
    """A key that is there and carries nothing is not an absent key.

    `port: ~` and `url: ''` used to be read as "this row says nothing", so
    the built-in URL was kept and the operator never learned that their row
    was ignored -- the silent fallback this PR set out to remove.
    """
    _contract(tmp_path, body)
    row = _digigraph_row(tmp_path)
    assert row.refusal is not None, why
    assert row.url is None
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_a_contract_row_without_a_url_or_a_port_still_keeps_the_built_in_url(tmp_path):
    """The control: an absent key still means "the row says nothing"."""
    _contract(tmp_path, "services:\n  - name: digigraph\n    profile: core\n")
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    assert row.url == "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz"


# --- the verb a contract row may probe with (DIG-4991) ----------------------
#
# A health probe reads, or writes a nonce it then reads back. It never deletes,
# replaces or patches anything: a `method:` in a contract is the operator
# saying what the gate will do to their service, and a typo there is a
# destructive request against a live endpoint. The set is therefore closed and
# a row outside it is refused, not coerced to GET -- a silently probed GET
# would report a verdict on a request the operator never wrote.


@pytest.mark.parametrize("method", ["GET", "POST", "get", "post", "Get", "pOsT", " get "])
def test_a_contract_row_may_probe_with_get_or_post(tmp_path, method):
    _contract(tmp_path, f"services:\n  - name: digigraph\n    method: '{method}'\n")
    row = _digigraph_row(tmp_path)
    assert row.refusal is None
    # The verb that was checked is the verb that is probed: a padded " get "
    # read as "GET" here and probed as " GET " would be a different request.
    # The scalar is quoted so YAML hands the row exactly what was written --
    # unquoted, " get " never reaches the row and the padding is never tested.
    assert row.method == ("GET" if method.strip().upper() == "GET" else "POST")


def test_the_probe_verb_set_is_closed():
    """Only GET and POST, enumerated: a verb added by accident fails here."""
    assert contracts.PROBE_METHODS == frozenset({"GET", "POST"})


@pytest.mark.parametrize("method", ["DELETE", "PUT", "PATCH", "HEAD", "OPTIONS", "TRACE"])
def test_a_contract_row_may_not_probe_with_any_other_verb(tmp_path, method):
    """The refusal names the verb, so the operator can see the typo."""
    _contract(tmp_path, f"services:\n  - name: digigraph\n    method: {method}\n")
    row = _digigraph_row(tmp_path)
    assert row.refusal is not None
    assert method in row.refusal
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


def test_a_contract_method_that_is_not_a_verb_is_refused(tmp_path):
    """A list is not a method, and it is refused rather than stringified."""
    _contract(tmp_path, "services:\n  - name: digigraph\n    method: [GET]\n")
    row = _digigraph_row(tmp_path)
    assert row.refusal is not None
    with pytest.raises(contracts.ContractRefusal):
        contracts.resolve(row, {})


# --- a credential in a URL is never printed (DIG-4991) ---------------------
#
# #6207 refuses userinfo in a probe URL. A refusal is only half of it: the
# reason is printed by `dt urls`, by `dt status` and in the gate's JSON, so the
# message must not carry the password it refused. Redaction keeps the address
# (the operator still needs to know which row and which host) and drops the
# credential.


def test_redact_userinfo_keeps_the_address_and_drops_the_credential():
    assert (
        contracts.redact_userinfo("http://operator:s3cret@127.0.0.1:9000/healthz")
        == "http://***@127.0.0.1:9000/healthz"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9000/healthz",
        "http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz",
    ],
)
def test_redact_userinfo_leaves_a_url_without_userinfo_alone(url):
    """The control: redaction is not a rewrite of every URL that passes."""
    assert contracts.redact_userinfo(url) == url


def test_a_refusal_never_echoes_the_userinfo_it_refused(tmp_path):
    """The refusal names the row and the host, and not the password."""
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    url: http://operator:s3cret@127.0.0.1:9000/healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    message = str(caught.value)
    assert "s3cret" not in message
    assert "***" in message
    assert "127.0.0.1" in message


@pytest.mark.parametrize(
    "url",
    [
        # a password, a bare token, and a token with an '@' inside it
        "http://operator:s3cret@127.0.0.1:9000/x",
        "http://token@127.0.0.1:9000/x",
        "http://operator:p@ss@127.0.0.1:9000/x",
        # shapes whose userinfo is not in a parseable authority
        "operator:s3cret@127.0.0.1:9000/x",
        "http:/operator:s3cret@127.0.0.1:9000/x",
        # the same typo with a doubled slash after it: the text before the
        # first '//' is where the credential sits, so no prefix carrying an
        # '@' may survive the fallback
        "http:/operator:s3cret@127.0.0.1:9000//healthz",
        "http://operator:p/a@127.0.0.1:9000/x",
        "http://operator:s3cret@[::1",
    ],
)
def test_redact_userinfo_drops_the_credential_and_keeps_the_address(url):
    """Every userinfo shape is redacted, whatever the URL parses into.

    The shapes that do not parse as an authority are the ones a typo makes:
    if redaction only handled the well-formed case, the message that refuses a
    typo would print the credential in the typo.
    """
    redacted = contracts.redact_userinfo(url)
    assert "s3cret" not in redacted
    assert "p@ss" not in redacted
    assert "token" not in redacted
    assert "***@" in redacted
    assert "127.0.0.1" in redacted or "[::1" in redacted


def test_redact_userinfo_leaves_a_url_whose_at_sign_is_not_userinfo_alone():
    """A query string may carry an '@'; it is not a credential."""
    url = "http://127.0.0.1:9000/x?next=a@b"
    assert contracts.redact_userinfo(url) == url


def test_redact_userinfo_passes_none_through():
    """Every ``Result`` with no URL depends on it; '' would print as a URL."""
    assert contracts.redact_userinfo(None) is None


def test_a_host_mismatch_refusal_names_no_credential(tmp_path):
    """The off-loopback arm is the one a userinfo URL reaches first.

    ``user:secret@evil.com`` is both off-loopback and userinfo, and the
    host-mismatch message is the one that prints the URL. It must not be the
    one that prints the password.
    """
    _contract(
        tmp_path,
        "services:\n"
        "  - name: digigraph\n"
        "    url: http://operator:s3cret@evil.com:9000/healthz\n",
    )
    row = _digigraph_row(tmp_path)
    with pytest.raises(contracts.ContractRefusal) as caught:
        contracts.resolve(row, {})
    message = str(caught.value)
    assert "s3cret" not in message
    # The host must be named as the host: the printed URL is parsed and its
    # authority compared, not substring-matched -- "evil.com" at an arbitrary
    # position inside a URL is not the host (CodeQL: incomplete URL substring
    # sanitization).
    shown = next(seg for seg in message.split("'") if "://" in seg)
    assert urlsplit(shown).hostname == "evil.com"
    assert "***@" in urlsplit(shown).netloc


@pytest.mark.parametrize(
    "template",
    [
        "http://operator:s3cret@127.0.0.1:${DT_BESPOKE_PORT:-8000}/x",
        "http://operator:s3cret@${DT_BESPOKE_HOST:-127.0.0.1}:8000/x",
    ],
)
def test_a_templated_url_refusal_names_no_credential(template):
    """The expand refusal prints the template; the template may carry a token."""
    check = contracts.Check(
        name="templated",
        kind="http",
        url=template,
        profiles=("all",),
        source="test fixture",
    )
    with pytest.raises(contracts.InvalidPort) as caught:
        contracts.resolve(check, {})
    assert "s3cret" not in str(caught.value)


def test_check_to_dict_carries_no_credential():
    """``Check.to_dict`` is the payload CI reads; it redacts like Result does."""
    check = contracts.Check(
        name="remote",
        kind="http",
        url="http://operator:s3cret@127.0.0.1:9000/x",
        profiles=("all",),
        source="test fixture",
    )
    assert "s3cret" not in str(check.to_dict())
    assert "***@" in str(check.to_dict())
