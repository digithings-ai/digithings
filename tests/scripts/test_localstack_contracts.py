"""Catalogue and preflight tests for the local self-host stack (DIG-2775, S7).

Two properties matter here. Every built-in default URL must trace to a source
in the tree, so a check cannot silently point at a port nothing serves; and a
preflight that finds nothing wrong must be proven able to find something.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
