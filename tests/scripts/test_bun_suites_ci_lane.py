"""Pin the bun-suites lane: every bun suite runs, and it runs in local-ci.

The gap this file exists to prevent: digivoice/tui, the four `clients/*` TUIs and
the two `packages/*` suites each declare `"test": "bun test"`. Their only lanes
were the GitHub workflows `test-bun-suites.yml` and `test-clients-tui.yml`
(DIG-2940 / DIG-2072), and both are retired with Actions (DIG-3604 / DIG-4454).
From then until DIG-5203 nothing ran them: the required `local-ci` check went
green on PR #6271 while digichat-tui's 71 tests (70 pass, 1 fail) only ever ran
by hand.

The lane is therefore `scripts/local-ci/local_ci.py` now, driven by the
`bun_suites` block of `scripts/ci_paths.yaml`, and the assertions below are the
four ways it can rot silently: a suite moves and the list no longer names it, a
suite loses its `bun test` script, a package with a bun suite lands outside the
trigger list (a new client), or the runner stops reading the list at all. Each
one goes red here rather than in a receipt that says nothing.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"
LOCAL_CI = REPO_ROOT / "scripts" / "local-ci" / "local_ci.py"

# Every suite the lane covers, as repo-relative package directories. `digivoice/tui`
# is the pre-move TUI (#5548 moved the live client to clients/digivoice-tui); the
# retired lane ran it and this one keeps it rather than shrink coverage quietly.
SUITES = (
    "digivoice/tui",
    "clients/digichat-tui",
    "clients/digiquant-tui",
    "clients/digivoice-tui",
    "clients/digichat-devkit",
    "packages/surface-config",
    "packages/hero-banner",
)


def _suite_dirs_from_ci_paths() -> list[str]:
    """The suite directories the list names: `<root>/<name>/**`, two segments.

    A broad trigger like `clients/**` fires the gate but names no suite; the
    runner treats anything else the same way (see bun_suite_dirs).
    """
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["bun_suites"]
    out = []
    for glob in globs:
        if not glob.endswith("/**"):
            continue
        suite = glob[:-3]
        if suite and not set(suite) & set("*?") and len(suite.split("/")) == 2:
            out.append(suite)
    return out


def _bun_test_packages() -> set[str]:
    """Every package under clients/* or packages/* that declares `bun test`.

    Mirrors local_ci.bun_test_packages, which gates these even when the list has
    not caught up: a new client must not enter ungated.
    """
    found = set()
    for root in ("clients", "packages"):
        for pkg in sorted((REPO_ROOT / root).glob("*/package.json")):
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if data.get("scripts", {}).get("test") == "bun test":
                found.add(f"{root}/{pkg.parent.name}")
    return found


def _runner_constant(name: str):
    tree = ast.parse(LOCAL_CI.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"local_ci.py defines no {name}")


def test_bun_suites_are_not_vanished() -> None:
    """Guards the guard.

    Every assertion below iterates over SUITES, so a renamed or moved suite
    would make the coverage checks quietly vacuous instead of red. A future
    move must update the filter and this file together.
    """
    for suite in SUITES:
        pkg = REPO_ROOT / suite / "package.json"
        assert pkg.is_file(), (
            f"{suite}/package.json is gone — if the suite moved, update "
            "scripts/ci_paths.yaml and this file rather than letting the "
            "coverage checks go quietly vacuous"
        )
        data = json.loads(pkg.read_text(encoding="utf-8"))
        assert data.get("scripts", {}).get("test") == "bun test", (
            f'{suite} no longer declares `"test": "bun test"` — the gate '
            "covers it for nothing; update the list or the manifest"
        )


def test_ci_paths_covers_every_suite() -> None:
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["bun_suites"]
    for suite in SUITES:
        assert f"{suite}/**" in globs, f"bun_suites must match {suite}/**; got {globs}"


def test_every_bun_test_package_is_covered() -> None:
    """No package with a bun suite may sit outside the list unnoticed.

    The runner discovers these itself, so the hole closed by DIG-5203 is a
    client that lands with a bun suite and no `clients/**` trigger: its first PR
    would touch no listed path and the required check would go green without
    running a single test. The discovery plus this assertion keeps the list
    honest as new packages land.
    """
    packages = _bun_test_packages()
    assert packages, "no bun-test packages found under clients/* or packages/*"
    missing = packages - set(_suite_dirs_from_ci_paths())
    assert not missing, f"every bun-test package must be named in bun_suites; missing: {sorted(missing)}"
    assert packages <= set(SUITES), f"SUITES is stale; add {sorted(packages - set(SUITES))} to it"


def test_clients_glob_fires_the_gate_for_a_new_client() -> None:
    """A new client's first PR touches paths no suite entry names.

    `clients/**` is what fires the gate for it; without the entry the gate sees
    no hit, runs nothing, and still reports green.
    """
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["bun_suites"]
    assert "clients/**" in globs, (
        "bun_suites needs a clients/** trigger, or a new client's first PR "
        "never fires the bun gate"
    )


def test_ci_paths_has_no_suite_local_ci_would_not_run() -> None:
    """The list and the runner's fallback are the same set of suites.

    local_ci reads the block, so a suite in the block but missing from
    BUN_SUITE_DIRS still runs — but a checkout whose block is missing or
    unreadable falls back to BUN_SUITE_DIRS, and the two drifting means the
    fallback silently covers less than the list says.
    """
    assert set(_suite_dirs_from_ci_paths()) == set(_runner_constant("BUN_SUITE_DIRS"))


def test_local_ci_reads_the_suite_list_and_runs_it() -> None:
    src = LOCAL_CI.read_text(encoding="utf-8")
    assert 'parse_ci_paths_block(f.read(), "bun_suites")' in src, (
        "local-ci must read the suite list from scripts/ci_paths.yaml"
    )
    assert "def run_bun_suites(" in src, "local-ci has no bun-suite runner"
    assert "for d in bun_suites_to_run(wt):" in src, (
        "the runner must also run packages it discovers in the tree, not just "
        "the ones the list names"
    )
    assert "run_bun_suites(WT, step, out, fails)" in src, (
        "the runner exists but run_checks never calls it: the gate would be dead code"
    )
    assert "success_desc(" in src, (
        "the receipt must name the suites that ran, or say `bun: none`"
    )


def test_ci_paths_filter_matches_each_suite() -> None:
    """The filter must match each suite's files, or the gate never fires for it.

    A narrower glob can silently exclude a suite's tests or its lockfile, and
    the gate then goes green without running on the change that should have
    triggered it.
    """
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["bun_suites"]
    for suite in SUITES:
        for probe in (f"{suite}/package.json", f"{suite}/src/anything.ts"):
            assert probe in globs or any(
                probe.startswith(glob.rstrip("**").rstrip("/")) for glob in globs
            ), f"{probe} matches no bun_suites glob; gate would not fire for it"


def test_standalone_suites_commit_a_lockfile() -> None:
    """local-ci installs every non-workspace suite with --frozen-lockfile.

    The `clients/*` packages and digivoice/tui are standalone bun packages, so a
    missing lockfile means the runner fails them by name
    (`bun-install:<suite>`) instead of testing whatever is lying around. The
    `packages/*` suites are workspaces of the root package.json: their deps come
    from the root `npm ci`, and `bun install` there would install the whole
    monorepo (the retired lane exempted them for exactly that reason).
    """
    workspaces = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["workspaces"]
    for suite in SUITES:
        workspace = any(
            suite.split("/")[0] == glob.rstrip("/*") for glob in workspaces
        )
        lockfile = REPO_ROOT / suite / "bun.lock"
        if workspace:
            continue
        assert lockfile.is_file(), (
            f"{suite} is not a root workspace but commits no bun.lock — "
            "`bun install --frozen-lockfile` fails, so its suite never runs"
        )
