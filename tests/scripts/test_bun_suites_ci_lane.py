"""Pin DIG-2940: every bun suite runs `bun test` in CI, and stays in the lane.

The gap this file exists to prevent: digivoice/tui, clients/digichat-tui and
packages/surface-config each declared `"test": "bun test"` and no workflow in
.github/workflows mentioned the bun tool at all, so every green number reported
for these suites was a developer-local run that only the developer who ran it
could verify. A break in any of them was found by a user, not by CI.

So the assertion is not "the lane passes" — CI cannot assert that about itself —
it is that the lane still exists, is still wired into the paths filter, and still
covers every suite it was built for. Those three can all rot silently, and each
one rotting means a suite ships untested and green, which is the exact failure
DIG-2940 was raised for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-bun-suites.yml"

# The three suites DIG-2940 covers, as repo-relative package directories.
SUITES = (
    "digivoice/tui",
    "clients/digichat-tui",
    "packages/surface-config",
)

# Suites with zero dependencies skip the install step (see the workflow): there
# is nothing to install, and `bun install` there would walk up to the repo-root
# workspace and install the whole monorepo instead.
NO_INSTALL_SUITES = ("packages/surface-config",)


def test_bun_suites_are_not_vanished() -> None:
    """Guards the guard.

    Every assertion below iterates over SUITES, so a renamed or moved suite
    would make the coverage checks quietly vacuous instead of red. A future
    move must update the lane, the filter and this file together.
    """
    for suite in SUITES:
        pkg = REPO_ROOT / suite / "package.json"
        assert pkg.is_file(), (
            f"{suite}/package.json is gone — if the suite moved, update "
            "test-bun-suites.yml, scripts/ci_paths.yaml and this file rather "
            "than letting the coverage checks go quietly vacuous"
        )
        data = json.loads(pkg.read_text(encoding="utf-8"))
        assert data.get("scripts", {}).get("test") == "bun test", (
            f'{suite} no longer declares `"test": "bun test"` — the lane '
            "covers it for nothing; update the matrix or the manifest"
        )


def test_ci_paths_covers_bun_suites() -> None:
    paths = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))
    assert "bun_suites" in paths, "scripts/ci_paths.yaml has no bun_suites filter"
    globs = paths["bun_suites"]
    for suite in SUITES:
        assert f"{suite}/**" in globs, f"bun_suites must match {suite}/**; got {globs}"
    assert ".github/workflows/test-bun-suites.yml" in globs, (
        "a change to the lane itself must fire the lane"
    )


def test_ci_paths_filter_matches_each_suite() -> None:
    """The filter must actually match each suite's files under dorny/paths-filter.

    A narrower glob can silently exclude a suite's tests or its lockfile, and
    the lane then goes green without running on the change that should have
    triggered it.
    """
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["bun_suites"]
    for suite in SUITES:
        for probe in (f"{suite}/package.json", f"{suite}/src/anything.ts"):
            assert any(
                probe == glob or probe.startswith(glob.rstrip("**").rstrip("/")) for glob in globs
            ), f"{probe} matches no bun_suites glob; lane would not fire for it"


def test_ci_yml_calls_the_lane() -> None:
    ci = CI_YML.read_text(encoding="utf-8")
    # The generator rewrites only the embedded dorny block. The outputs map and
    # the calling job are hand-written, so they are the parts that can rot while
    # `--check` stays green.
    assert "bun_suites: ${{ steps.filter.outputs.bun_suites }}" in ci, (
        "ci.yml changes job does not export bun_suites — the lane can never run"
    )
    assert "uses: ./.github/workflows/test-bun-suites.yml" in ci, (
        "ci.yml never calls test-bun-suites.yml"
    )
    assert "needs.changes.outputs.bun_suites == 'true'" in ci, (
        "the bun-suites job is not gated on the paths filter"
    )


def test_lane_runs_tests_for_every_suite() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for suite in SUITES:
        assert f"- dir: {suite}" in text, (
            f"{suite} declares a bun test script but is not in the lane matrix"
        )
    assert "bun install --frozen-lockfile" in text, (
        "install must be from the committed lockfile so a tool release cannot "
        "change what runs here (the #1701/#1705/#1711 rule)"
    )
    assert "bun run test" in text, "the lane must run each manifest's own test script"


def test_lane_version_pins_bun() -> None:
    """Unpinned bun is the repo's documented #1701/#1705/#1711 failure mode."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "oven-sh/setup-bun@" in text
    assert 'bun-version: "latest"' not in text, (
        "bun-version must be pinned; AGENTS.md requires pinning CI tooling because "
        "an unpinned tool changing under a green build caused #1701/#1705/#1711"
    )
    assert 'bun-version: "1.' in text, "pin to a concrete version, not a range"


def test_suites_with_dependencies_commit_a_lockfile() -> None:
    """The lane installs with --frozen-lockfile, which fails without one.

    A new dependency added without its lockfile would make the lane red on
    arrival — this fails first, at the commit that adds the dependency,
    naming the missing file.
    """
    for suite in SUITES:
        pkg = json.loads((REPO_ROOT / suite / "package.json").read_text(encoding="utf-8"))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        lockfile = REPO_ROOT / suite / "bun.lock"
        if suite in NO_INSTALL_SUITES:
            assert not deps, (
                f"{suite} now declares dependencies {sorted(deps)} but the lane "
                f"skips its install step — commit a bun.lock for it and drop the "
                f"matrix condition in test-bun-suites.yml"
            )
        else:
            assert lockfile.is_file(), (
                f"{suite} has dependencies but no committed bun.lock — the lane's "
                f"--frozen-lockfile install fails without it"
            )


def test_no_install_exemptions_stay_zero_dependency() -> None:
    """The install skip is load-bearing, not convenience.

    `bun install` in a dependency-free directory walks up to the repo-root
    workspace and installs the whole monorepo (observed: 1288 packages plus an
    unwanted root bun.lock). The exemption must never cover a suite that
    actually needs an install, or that suite tests against whatever happens to
    be lying around.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    for suite in NO_INSTALL_SUITES:
        assert f"matrix.dir != '{suite}'" in text, (
            f"{suite} is meant to skip the install step but the lane no longer "
            f"exempts it — or the exemption was removed while this file still lists it"
        )
