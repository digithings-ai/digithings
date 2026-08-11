"""Structural + behavioral pins for deploy-digichat-cloudflare-container.yml (#2199).

Before this workflow, deploying the digithings.ai digichat Cloudflare
Container (the live `/embed` widget) was manual-only (`npx wrangler deploy`
from a developer machine) -- verified no workflow anywhere ran it. This
covers two failure classes: the workflow definition drifting away from its
own documented triggers/gating, and the gating shell script itself (executed
directly, not re-implemented in Python, so a change to the real script is
what this test actually exercises).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any  # score:allow untyped any — parsed YAML document

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-digichat-cloudflare-container.yml"


def _spec() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _deploy_job() -> dict[str, Any]:
    return _spec()["jobs"]["deploy"]


def _gating_step() -> dict[str, Any]:
    for step in _deploy_job()["steps"]:
        if step.get("id") == "check":
            return step
    raise AssertionError("no step with id 'check' found in the deploy job")


# ── workflow wiring: a deploy that never runs deploys nothing ────────────────


def test_the_workflow_exists_and_triggers_on_push_to_main() -> None:
    spec = _spec()
    triggers = spec.get("on") or spec.get(True)  # PyYAML parses bare `on:` as True
    assert "push" in triggers
    assert triggers["push"]["branches"] == ["main"]


def test_the_workflow_can_also_be_dispatched_manually() -> None:
    triggers = _spec().get("on") or _spec().get(True)
    assert "workflow_dispatch" in triggers


def test_the_paths_filter_covers_every_signal_the_gate_checks() -> None:
    """The gate reads digichat's version and diffs the wrapper's own paths --
    if either falls out of this filter, the workflow never runs to check it."""
    triggers = _spec().get("on") or _spec().get(True)
    paths = set(triggers["push"]["paths"])
    assert "frontend/digichat/package.json" in paths
    assert "frontend/digichat-cloudflare/**" in paths
    assert "Dockerfile.digichat-cloudflare" in paths


def test_the_checkout_fetches_full_history() -> None:
    """The gating step diffs against `before` -- a shallow (default depth-1)
    clone would not have fetched it, and the diff would silently see nothing."""
    checkout = next(
        s for s in _deploy_job()["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0


def test_the_deploy_step_is_gated_on_the_check_step() -> None:
    deploy_step = next(
        s
        for s in _deploy_job()["steps"]
        if s.get("uses", "").startswith("cloudflare/wrangler-action")
    )
    assert deploy_step["if"] == "steps.check.outputs.deploy == 'true'"


def test_the_deploy_step_targets_the_right_directory_and_command() -> None:
    deploy_step = next(
        s
        for s in _deploy_job()["steps"]
        if s.get("uses", "").startswith("cloudflare/wrangler-action")
    )
    assert deploy_step["with"]["workingDirectory"] == "frontend/digichat-cloudflare"
    assert deploy_step["with"]["command"] == "deploy"


def test_the_deploy_step_uses_repo_secrets_not_hardcoded_credentials() -> None:
    deploy_step = next(
        s
        for s in _deploy_job()["steps"]
        if s.get("uses", "").startswith("cloudflare/wrangler-action")
    )
    assert deploy_step["with"]["apiToken"] == "${{ secrets.CLOUDFLARE_API_TOKEN }}"
    assert deploy_step["with"]["accountId"] == "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}"


def test_the_deploy_step_pins_a_wrangler_version_that_supports_containers() -> None:
    """wrangler-action's own default (no `wranglerVersion` given) installed a
    hardcoded 3.90.0 on this workflow's first real run -- 3.x predates Cloudflare
    Containers entirely and silently ignored the `[[containers]]` config instead
    of failing, deploying only the Worker routing shell and never rebuilding the
    actual Container image. Must match (or exceed) the floor the project's own
    frontend/digichat-cloudflare/package.json declares."""
    deploy_step = next(
        s
        for s in _deploy_job()["steps"]
        if s.get("uses", "").startswith("cloudflare/wrangler-action")
    )
    pinned = deploy_step["with"]["wranglerVersion"]
    assert pinned, "wranglerVersion must be set explicitly, not left to the action's default"

    declared = json.loads(
        (REPO_ROOT / "frontend" / "digichat-cloudflare" / "package.json").read_text(
            encoding="utf-8"
        )
    )["devDependencies"]["wrangler"]
    assert pinned == declared, (
        f"workflow pins wrangler {pinned!r} but package.json declares {declared!r} -- "
        "keep both in agreement so a local `npm ci` and the CI deploy resolve the same wrangler."
    )


def test_workspace_dependencies_are_installed_before_deploying() -> None:
    """frontend/digichat-cloudflare has no lockfile of its own -- it's an npm
    workspace under the root package-lock.json. Without a real `npm ci` at repo
    root first, wrangler 4.x fails loudly trying to bundle
    src/index.ts's `@cloudflare/containers` import (verified locally: `Could not
    resolve "@cloudflare/containers"`) because node_modules was never populated."""
    steps = _deploy_job()["steps"]
    deploy_index = next(
        i for i, s in enumerate(steps) if s.get("uses", "").startswith("cloudflare/wrangler-action")
    )
    install_step = next(
        (s for s in steps[:deploy_index] if s.get("run", "").strip() == "npm ci"),
        None,
    )
    assert install_step is not None, "no `npm ci` step found before the Deploy step"
    # Gated the same as the deploy itself -- no reason to spend the install time
    # (or trigger `cache: npm`'s restore) when the gate already decided to skip.
    assert install_step["if"] == "steps.check.outputs.deploy == 'true'"


def test_the_gate_reads_before_via_env_not_inline_interpolation() -> None:
    """`github.event.before` must reach the shell as `$BEFORE` via `env:`, not
    interpolated straight into `run:` -- the injection-safe pattern for any
    workflow-context value, even one as constrained as a commit SHA."""
    step = _gating_step()
    assert step["env"]["BEFORE"] == "${{ github.event.before }}"
    assert "github.event.before" not in step["run"]


def test_the_concurrency_group_prevents_overlapping_deploys() -> None:
    concurrency = _spec()["concurrency"]
    assert concurrency["group"] == "deploy-digichat-cloudflare-container"
    assert concurrency["cancel-in-progress"] is False


# ── the gating script itself, executed for real ──────────────────────────────


def _run_gate(repo: Path, before: str) -> str:
    """Extract and run the exact `check` step's script against a scratch repo.

    Executes the real script text from the workflow file, not a
    reimplementation -- a change to the actual gating logic is what makes
    this test fail, not a change to a parallel copy of it. `GITHUB_OUTPUT`
    is a real file, matching the runner's actual contract: the script writes
    `deploy=...` there, not to stdout.
    """
    script = _gating_step()["run"]
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as output_file:
        output_path = output_file.name
    try:
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=repo,
            env={
                **os.environ,
                "BEFORE": before,
                "GITHUB_SHA": "HEAD",
                "GITHUB_OUTPUT": output_path,
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"gate script exited {result.returncode}: {result.stderr}"
        outputs = Path(output_path).read_text(encoding="utf-8")
        line = next(line for line in outputs.splitlines() if line.startswith("deploy="))
        return line.split("=", 1)[1]
    finally:
        Path(output_path).unlink(missing_ok=True)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def scratch_repo() -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "config", "user.name", "test")
        (repo / "frontend" / "digichat").mkdir(parents=True)
        (repo / "frontend" / "digichat-cloudflare").mkdir(parents=True)
        yield repo


def _write_version(repo: Path, version: str) -> None:
    (repo / "frontend" / "digichat" / "package.json").write_text(f'{{"version": "{version}"}}\n')


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.mark.unit
def test_gate_skips_when_neither_version_nor_wrapper_changed(scratch_repo: Path) -> None:
    _write_version(scratch_repo, "1.0.0")
    before = _commit(scratch_repo, "initial")
    # An unrelated file changes; version and wrapper both stay untouched.
    (scratch_repo / "frontend" / "digichat" / "README.md").write_text("noop\n")
    _commit(scratch_repo, "docs: noop")

    assert _run_gate(scratch_repo, before) == "false"


@pytest.mark.unit
def test_gate_refuses_to_guess_when_version_field_is_missing(scratch_repo: Path) -> None:
    """`jq -r .version` on a package.json missing the field yields the literal
    string "null", which would silently read as "changed" against any real
    prior version -- the gate must fail loudly instead of guessing."""
    _write_version(scratch_repo, "1.0.0")
    before = _commit(scratch_repo, "initial")
    (scratch_repo / "frontend" / "digichat" / "package.json").write_text('{"name": "digichat"}\n')
    _commit(scratch_repo, "oops: dropped the version field")

    script = _gating_step()["run"]
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as output_file:
        output_path = output_file.name
    try:
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=scratch_repo,
            env={
                **os.environ,
                "BEFORE": before,
                "GITHUB_SHA": "HEAD",
                "GITHUB_OUTPUT": output_path,
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "no .version field" in result.stderr
    finally:
        Path(output_path).unlink(missing_ok=True)


@pytest.mark.unit
def test_gate_deploys_when_the_digichat_version_bumps(scratch_repo: Path) -> None:
    _write_version(scratch_repo, "1.0.0")
    before = _commit(scratch_repo, "initial")
    _write_version(scratch_repo, "1.1.0")
    _commit(scratch_repo, "chore(develop): release digichat 1.1.0")

    assert _run_gate(scratch_repo, before) == "true"


@pytest.mark.unit
def test_gate_deploys_when_only_the_wrapper_itself_changes(scratch_repo: Path) -> None:
    """The wrapper has no version field release-please tracks -- a fix made
    purely to it must still trigger a deploy."""
    _write_version(scratch_repo, "1.0.0")
    before = _commit(scratch_repo, "initial")
    (scratch_repo / "frontend" / "digichat-cloudflare" / "src.ts").write_text("// fix\n")
    _commit(scratch_repo, "fix(digichat-cloudflare): router bug")

    assert _run_gate(scratch_repo, before) == "true"


@pytest.mark.unit
def test_gate_deploys_when_before_is_unresolvable(scratch_repo: Path) -> None:
    """A force-push, history rewrite, or the all-zero sentinel SHA for a new
    branch must fail open to a deploy, not silently skip one."""
    _write_version(scratch_repo, "1.0.0")
    _commit(scratch_repo, "initial")

    assert _run_gate(scratch_repo, "0" * 40) == "true"
    assert _run_gate(scratch_repo, "0" * 40) == "true"  # sentinel, not just any bad SHA
    assert _run_gate(scratch_repo, "") == "true"
