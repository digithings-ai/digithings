"""Pin DIG-2072: every bun client runs `bun test` in CI, and stays in the lane.

The gap this file exists to prevent: `clients/digiquant-tui` had 139+ tests and
no CI lane at all. `scripts/ci_paths.yaml` had no `clients/**` entry and no
workflow in .github/workflows/ mentioned bun, so every green number reported for
the TUI clients was a developer-local run. A reviewer asking "would this suite
notice a defect?" produced a real test (fx-footer.test.tsx, #183) that nothing
enforced.

So the assertion is not "the lane passes" — CI cannot assert that about itself —
it is that the lane still exists, is still wired into the paths filter, and still
covers every client that declares a test script. Those three can all rot silently,
and each one roting means a client ships untested and green, which is the exact
failure #2072 was raised for.

Follows the test_frontend_dashboard_workspace.py shape (same directory of
concern: CI wiring that is invisible when it is wrong).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIENTS = REPO_ROOT / "clients"
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-clients-tui.yml"


def _bun_clients() -> dict[str, Path]:
    """clients/ dirs whose package.json declares `"test": "bun test"`."""
    found: dict[str, Path] = {}
    for pkg in sorted(CLIENTS.glob("*/package.json")):
        data = json.loads(pkg.read_text(encoding="utf-8"))
        if data.get("scripts", {}).get("test") == "bun test":
            found[pkg.parent.name] = pkg
    return found


def test_clients_directory_exists() -> None:
    assert CLIENTS.is_dir(), "clients/ must exist — the gap was never that it was empty"


def test_bun_clients_are_not_vanished() -> None:
    """Guards the guard.

    _bun_clients() returning {} would make every assertion below vacuously true:
    the matrix-completeness test, the filter test, all of it. A future rename or
    a move out of clients/ would then delete the coverage silently and leave a
    green suite behind, which is the failure mode this file is about.
    """
    found = _bun_clients()
    assert found, (
        'no clients/*/package.json declares "test": "bun test" — if the clients '
        "moved or were renamed, update test-clients-tui.yml and this file rather "
        "than letting the coverage checks go quietly vacuous"
    )
    assert "digiquant-tui" in found, "the client DIG-2072 was raised for must still be here"


def test_ci_paths_covers_client_tree() -> None:
    paths = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))
    assert "clients_tui" in paths, "scripts/ci_paths.yaml has no clients_tui filter"
    globs = paths["clients_tui"]
    assert "clients/**" in globs, (
        f"clients_tui must match the whole client tree, not individual globs; got {globs}"
    )
    assert ".github/workflows/test-clients-tui.yml" in globs, (
        "a change to the lane itself must fire the lane"
    )


def test_clients_tui_filter_covers_every_bun_client() -> None:
    """The filter must actually match each client's path under dorny/paths-filter.

    A narrower glob (one directory, or `clients/**/src/**`) can silently exclude
    a new client's tests or its lockfile, and the lane then goes green without
    running on the change that should have triggered it.
    """
    globs = yaml.safe_load(CI_PATHS.read_text(encoding="utf-8"))["clients_tui"]
    for client, pkg in _bun_clients().items():
        for probe in (f"clients/{client}/{pkg.name}", f"clients/{client}/src/anything.ts"):
            assert any(
                probe == glob or probe.startswith(glob.rstrip("**").rstrip("/")) for glob in globs
            ), f"{probe} matches no clients_tui glob; lane would not fire for it"


def test_ci_yml_calls_the_lane() -> None:
    ci = CI_YML.read_text(encoding="utf-8")
    # The generator rewrites only the embedded dorny block. The outputs map and
    # the calling job are hand-written, so they are the parts that can rot while
    # `--check` stays green.
    assert "clients_tui: ${{ steps.filter.outputs.clients_tui }}" in ci, (
        "ci.yml changes job does not export clients_tui — the lane can never run"
    )
    assert "uses: ./.github/workflows/test-clients-tui.yml" in ci, (
        "ci.yml never calls test-clients-tui.yml"
    )
    assert "needs.changes.outputs.clients_tui == 'true'" in ci, (
        "the clients-tui job is not gated on the paths filter"
    )


def test_lane_runs_tests_for_every_bun_client() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for client in _bun_clients():
        assert f"- {client}" in text, (
            f"clients/{client} declares a bun test script but is not in the matrix"
        )
    assert "bun install --frozen-lockfile" in text, (
        "install must be from the committed lockfile so a tool release cannot "
        "change what runs here (the #1701/#1705/#1711 rule)"
    )
    assert "bun run test" in text, "the lane must run the manifest's own test script"


def test_lane_version_pins_bun() -> None:
    """Unpinned bun is the repo's documented #1701/#1705/#1711 failure mode."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "oven-sh/setup-bun@" in text
    assert 'bun-version: "latest"' not in text, (
        "bun-version must be pinned; AGENTS.md requires pinning CI tooling because "
        "an unpinned tool changing under a green build caused #1701/#1705/#1711"
    )
    assert 'bun-version: "' in text and 'bun-version: "1.' in text, (
        "pin to a concrete version, not a range"
    )


def _commands() -> str:
    """The workflow with comment lines stripped.

    Several assertions below look for tokens that this file deliberately
    *mentions in prose* while explaining why it does not do the thing. Asserting
    on raw text then fails on the explanation rather than on a step — which is
    how `test_lane_has_no_typecheck_step` first went red on its own comment.
    """
    return "\n".join(
        line
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_lane_does_not_recover_the_matrix_from_expression_syntax() -> None:
    """Pins the bug that made this lane red on its first CI run.

    `matrix.client` is a SCALAR inside a matrixed job, so `toJSON(matrix.client)`
    is a quoted string like `"digiquant-tui"`, not an array. The first version of
    the coverage guard fed that value in as "the matrix", so each leg saw only
    itself and failed on its siblings — all three legs red, on a suite that passes
    locally. `join(matrix.client, ...)` is not the fix: actionlint rejects that
    overload (it takes a string, not an array). The guard reads the matrix out of
    the workflow file instead, which keeps one source of truth.
    """
    commands = _commands()
    assert "toJSON(matrix.client)" not in commands, (
        "toJSON(matrix.client) yields a quoted scalar, not an array — the "
        "coverage guard would see one client and fail on the others"
    )
    assert "join(matrix.client" not in commands, (
        "actionlint rejects join(array<string>) with a separator; it takes a "
        "string, so it cannot enumerate the matrix either"
    )


def test_coverage_guard_runs_once_not_per_matrix_leg() -> None:
    """Its verdict is a property of (matrix, tree), so it must not be per-leg."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    assert "client-coverage" in jobs, (
        "the matrix-completeness check must be its own job; inside the matrixed "
        "job it re-checks the same matrix against itself once per leg"
    )
    assert "matrix" not in jobs["client-coverage"].get("strategy", {}), (
        "client-coverage must not itself be matrixed — it runs once"
    )
    coverage_steps = jobs["client-coverage"]["steps"]
    assert not any("matrix.client" in str(s.get("with", "")) for s in coverage_steps)


def test_required_checks_covers_the_new_lane() -> None:
    """ci.yml has a drift guard that fails if a job is missing from this list.

    Adding a job to ci.yml without adding it to `required-checks.needs` fails the
    CI workflow's own "Verify needs list covers every job in this file" step —
    which is how the first run of this lane went red on an unrelated job. Caught
    here instead, before the push, because it is a plain list in a file we edit.
    """
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    needs = set(doc["jobs"]["required-checks"]["needs"])
    jobs = set(doc["jobs"]) - {"required-checks"}
    assert "clients-tui" in needs, (
        "required-checks.needs is missing clients-tui; the drift guard in "
        "required-checks fails the whole CI workflow when it is absent"
    )
    # Keep the assertion symmetrical with the guard this mirrors.
    assert not (needs - jobs), f"required-checks lists jobs that do not exist: {needs - jobs}"
    assert not (jobs - needs), f"required-checks is missing jobs: {jobs - needs}"


def test_lane_has_no_typecheck_step() -> None:
    """Documents why the lane is bun-test-only, so it is not added by accident.

    Each client tsconfig lists `bun` in `types`, but no package.json in this repo
    declares `@types/bun` or `bun-types`, so `bunx tsc --noEmit` fails
    `TS2688: Cannot find type definition file for 'bun'` on pristine HEAD of the
    base. Adding a type gate to the commit that introduces the lane would make it
    red on arrival and block the lane itself. The fix belongs in its own change,
    with the dependency decision made there.
    """
    # Strip comments first: this workflow's header explains at length why there
    # is no type gate, and asserting on raw text would fail on its own
    # explanation rather than on a step.
    commands = _commands()
    assert "tsc" not in commands and "typecheck" not in commands, (
        "this lane is intentionally bun test only — adding a type check here is "
        "red on arrival (TS2688, no @types/bun in any package.json); add it as a "
        "separate change that also fixes the missing dependency"
    )


def test_every_bun_client_commits_a_lockfile() -> None:
    """--frozen-lockfile fails rather than re-resolving, but only if the lock exists."""
    for client in _bun_clients():
        lock = CLIENTS / client / "bun.lock"
        assert lock.is_file(), (
            f"clients/{client} has no bun.lock; the lane installs with "
            "--frozen-lockfile and would fail"
        )
