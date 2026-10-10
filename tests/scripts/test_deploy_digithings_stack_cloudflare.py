"""Contract pins for the production deploy path (DIG-1569).

The incident this file exists to prevent: ``deploy-digithings-stack-cloudflare.yml``
triggered on ``pull_request`` + ``workflow_dispatch`` only, so **merging to main
deployed nothing**. The fix that retired unmasked customer PII from the stack
seed payload landed as ``da88fa71`` and production served the retiring container
(``shared-v16``) for ~19 hours after it — a fix present in main and absent from
production reads, from any audit, as an unremediated exposure.

A YAML trigger block is exactly the kind of thing that silently regresses: delete
one key and a merge deploys nothing again, with every test still green. So the
triggers are pinned here, plus the repo-wide invariant that closed out item 3 of
the issue: any workflow that can deploy must fire on ``push: main``.

The audit itself found exactly one defective workflow. The invariant test below
exists so the *next* one fails CI rather than production.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

# `make test-unit` and ci.yml both run `-m unit`; an unmarked file is deselected
# entirely, so an unmarked test is a test that never runs.
pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
STACK_WORKFLOW = WORKFLOWS_DIR / "deploy-digithings-stack-cloudflare.yml"

# Paths whose deployment is owned by Cloudflare's git integration, not by a
# workflow here. `gh pages deploy` in these files builds a PR preview; production
# digithings.ai / digiquant.io are built by the Cloudflare dashboard from `main`.
# Recorded from AGENTS.md § Deployments (static sites) and each file's header.
PAGES_GIT_INTEGRATION_WORKFLOWS = frozenset(
    {
        "deploy-digithings-cloudflare.yml",
        "deploy-digiquant-cloudflare.yml",
    }
)

# What "this workflow can change production" looks like in practice. Two forms:
# a shell deploy command in a `run:` step, and the wrangler-action composite with
# a deploy command — most of the repo's deploys are the latter, so matching only
# `run:` would let the invariant below pass vacuously for four of them.
DEPLOY_COMMAND = re.compile(
    r"(?:npx\s+(?:--no-install\s+)?wrangler\s+deploy|"
    r"wrangler\s+versions\s+deploy|"
    r"gh\s+pages\s+deploy)"
)
WRANGLER_ACTION = "cloudflare/wrangler-action"


def _triggers(spec: dict[str, Any]) -> dict[str, Any]:
    """PyYAML parses a bare `on:` key as boolean True."""
    return spec.get("on") or spec.get(True) or {}


def _steps(spec: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for job in (spec.get("jobs") or {}).values():
        steps.extend(job.get("steps") or [])
    return steps


def _run_scripts(spec: dict[str, Any]) -> list[str]:
    return [s["run"] for s in _steps(spec) if isinstance(s.get("run"), str)]


def _can_deploy(step: dict[str, Any]) -> bool:
    """True if this single step pushes something to production."""
    if isinstance(step.get("run"), str) and DEPLOY_COMMAND.search(step["run"]):
        return True
    if WRANGLER_ACTION in str(step.get("uses", "")):
        # wrangler-action's default command is `deploy`, so an omitted `command`
        # is a deploy too.
        command = str((step.get("with") or {}).get("command", "deploy"))
        if command.split()[0] in {"deploy", "versions"}:
            return True
    return False


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml"))


def _deployable_workflows() -> list[tuple[str, dict[str, Any]]]:
    """Every workflow containing a production-deploying command in a run step."""
    found: list[tuple[str, dict[str, Any]]] = []
    for path in _workflow_files():
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - malformed workflow, other tests own it
            continue
        if not isinstance(spec, dict):
            continue
        if any(_can_deploy(step) for step in _steps(spec)):
            found.append((path.name, spec))
    return found


# ── the stack workflow: a merge to main must deploy ─────────────────────────


def test_the_workflow_exists() -> None:
    assert STACK_WORKFLOW.exists(), f"missing {STACK_WORKFLOW}"


def test_it_triggers_on_push_to_main() -> None:
    """The DIG-1569 defect, pinned.

    Without this, a merge to main runs nothing: the fix lands in main and never
    reaches production, which is what happened to da88fa71.
    """
    triggers = _triggers(yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8")))
    assert "push" in triggers, (
        "deploy-digithings-stack-cloudflare.yml has no `push` trigger — merging to "
        "main deploys nothing (DIG-1569)"
    )
    assert triggers["push"]["branches"] == ["main"]


def test_it_still_triggers_on_pull_request_and_manual_dispatch() -> None:
    triggers = _triggers(yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8")))
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    assert (
        _triggers(yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8")))["workflow_dispatch"][
            "inputs"
        ]["ref"]["default"]
        == "main"
    )


def test_push_and_pull_request_path_filters_are_identical() -> None:
    """The merge path and the review path must not drift apart.

    The two path lists are written out twice on purpose (no YAML anchor — an
    anchor here is invisible to review). That makes drift possible, so it is
    pinned: if a path is added to one and not the other, the review stops
    validating what the merge deploys.
    """
    triggers = _triggers(yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8")))
    assert triggers["push"]["paths"] == triggers["pull_request"]["paths"]


def test_the_path_filter_still_covers_the_stack_and_its_deploy_command() -> None:
    triggers = _triggers(yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8")))
    paths = set(triggers["push"]["paths"])
    assert "apps/digithings-stack-cloudflare/**" in paths
    assert "Dockerfile.digithings-stack-cloudflare" in paths
    assert ".github/workflows/deploy-digithings-stack-cloudflare.yml" in paths


# ── the job split: pull requests validate, only main dispatches ──────────────


def _stack_spec() -> dict[str, Any]:
    return yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8"))


def test_a_pull_request_cannot_reach_the_deploy_job() -> None:
    """`deploy` must be false for a pull_request event."""
    condition = _stack_spec()["jobs"]["deploy"]["if"]
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "pull_request" not in condition, (
        "the deploy job must not be reachable from a pull_request event"
    )


def test_deploy_waits_for_its_gate_job() -> None:
    jobs = _stack_spec()["jobs"]
    assert "check-deploy-gate" in jobs["deploy"]["needs"]
    assert jobs["deploy"]["needs"] != ["check"], (
        "on push there is no pull_request event, so `check` is skipped; deploy "
        "must depend on a gate that actually runs"
    )


def test_the_gate_job_does_not_depend_on_the_pull_request_only_check() -> None:
    """The bug that made this whole PR a no-op, pinned where it happened.

    ``check-deploy-gate`` originally carried ``needs: [check]``. ``check`` is
    ``if: github.event_name == 'pull_request'``, and GitHub skips every downstream
    job when a need is skipped. So on a merge to main: ``check`` skipped ->
    ``check-deploy-gate`` skipped -> ``deploy`` skipped. The push trigger was
    present and did nothing.

    ``actionlint`` exits 0 on this file, and the previous version of this suite
    read only ``jobs["deploy"]["needs"]`` -- never this one -- so all 56 tests
    passed against a workflow that could not deploy. ci.yml depends on ~23
    path-filtered jobs and survives only because its consumer declares
    ``if: always()``.
    """
    jobs = _stack_spec()["jobs"]
    gate_needs = jobs["check-deploy-gate"].get("needs") or []
    assert not gate_needs, (
        f"check-deploy-gate depends on {gate_needs}. Anything it needs is skipped on "
        "the event that should deploy, and a skipped need skips this job, which then "
        "skips `deploy`. This is DIG-1569 reproduced inside its own fix."
    )
    # And nothing it needs may itself be scoped to a pull_request-only event.
    for need in gate_needs:
        assert "pull_request" not in str(jobs.get(need, {}).get("if", "")), need


def test_the_push_filter_covers_every_tree_the_image_bakes_in() -> None:
    """A merge that changes shipped code must not deploy nothing.

    The deployed image's build context is the repo root, so it copies from these
    trees. The original filter listed ``digiquant/Dockerfile.mcp`` and
    ``digivault/Dockerfile.mcp`` but none of the library source they COPY, so a
    merge touching ``digikey/**`` (JWT auth) or ``digisearch/seeds`` compiled into
    production and deployed nothing -- DIG-1569's defect class surviving the fix.
    """
    paths = set(_triggers(_stack_spec())["push"]["paths"])
    for tree in (
        "digibase",
        "digiclaw",
        "digifetch",
        "digigraph",
        "digikey",
        "digillm",
        "digismith",
        "digisearch",
        "digiquant",
        "digivault",
        "config",
        "infra",
        "scripts",
    ):
        assert f"{tree}/**" in paths, (
            f"{tree}/ is compiled into the deployed image but a push to main "
            f"changing it matches no path filter, so the merge deploys nothing"
        )


def test_the_pull_request_check_job_is_scoped_to_pull_requests() -> None:
    condition = _stack_spec()["jobs"]["check"]["if"]
    assert condition == "github.event_name == 'pull_request'"


def test_the_deploy_gate_job_runs_for_both_deploy_events() -> None:
    condition = _stack_spec()["jobs"]["check-deploy-gate"]["if"]
    assert condition == "github.event_name != 'pull_request'"


@pytest.mark.parametrize("job_name", ["check", "check-deploy-gate"])
def test_no_validation_job_contains_a_deploy_command(job_name: str) -> None:
    """Neither check job may ever gain a `wrangler deploy` in a run step."""
    scripts = _run_scripts({"jobs": {job_name: _stack_spec()["jobs"][job_name]}})
    assert not any(DEPLOY_COMMAND.search(script) for script in scripts)


def test_the_deploy_job_checks_out_the_ref_it_will_deploy() -> None:
    """push: `inputs.ref` is unset, so it must fall back to `github.sha`.

    Without the fallback the deploy job checks out the default branch — so a
    dispatch targeting a release branch would build and ship main instead.
    """
    checkout = next(
        step
        for step in _stack_spec()["jobs"]["deploy"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"]["ref"] == "${{ inputs.ref || github.sha }}"


def test_the_gate_job_checks_out_the_same_ref_as_the_deploy_job() -> None:
    """The gate must validate the bytes the deploy will ship."""
    gate_checkout = next(
        step
        for step in _stack_spec()["jobs"]["check-deploy-gate"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout")
    )
    assert gate_checkout["with"]["ref"] == "${{ inputs.ref || github.sha }}"


def test_the_deploy_job_is_still_behind_the_production_environment_gate() -> None:
    """Automation must not remove the human approval gate."""
    assert _stack_spec()["jobs"]["deploy"]["environment"] == "production"


def test_the_concurrency_group_stays_unique_per_run() -> None:
    """A shared group would restore #2541 now that a push trigger exists.

    The group is per-run on purpose and an earlier draft of this PR changed it to a
    per-ref group, reasoning that two quick merges would race two deploys onto one
    container name. That is the wrong trade: with `environment: production` and
    `cancel-in-progress: false`, a shared group means an unapproved run does not delay
    the workflow, it stops it, and every later run is evicted and reports `cancelled`
    with zero jobs (#2541, 15 days and migrations 066-070 on db-migrate). Before this PR
    that shape was latent because only a rare manual dispatch fired. With `push: main` it
    would be on the common path.

    `tests/scripts/test_workflow_environment_concurrency.py` already enforces this
    repo-wide and failed this branch. This test states the stack workflow's half of the
    reason next to the trigger that makes it matter.
    """
    group = str(_stack_spec()["concurrency"]["group"])
    assert "github.run_id" in group, (
        f"the concurrency group is {group!r}, which is shared across runs. Combined with "
        "`environment: production` and cancel-in-progress: false, one unapproved run stops "
        "every deploy behind it instead of delaying them (#2541)"
    )


def test_the_deploy_command_and_secrets_are_unchanged() -> None:
    """The push trigger must not have moved the wrangler invocation."""
    scripts = _run_scripts({"jobs": {"deploy": _stack_spec()["jobs"]["deploy"]}})
    joined = "\n".join(scripts)
    assert "npx wrangler deploy -c apps/digithings-stack-cloudflare/wrangler.toml" in joined
    assert "working-directory" not in joined, (
        "deploy runs from the repo root — the build context is resolved by "
        "wrangler.toml, not cwd (#4046)"
    )
    deploy_env = next(
        step["env"] for step in _stack_spec()["jobs"]["deploy"]["steps"] if step.get("env")
    )
    assert deploy_env["CLOUDFLARE_API_TOKEN"] == "${{ secrets.CLOUDFLARE_API_TOKEN }}"
    assert deploy_env["CLOUDFLARE_ACCOUNT_ID"] == "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}"


# ── repo-wide invariant: anything that deploys must fire on push: main ───────


def test_the_audit_found_at_least_the_workflows_it_should_have() -> None:
    """Guards against the discovery helper silently returning nothing.

    If a future edit breaks the `wrangler deploy` detection, the invariant test
    below would pass vacuously. This asserts the fixture set is non-trivial.
    """
    names = {name for name, _ in _deployable_workflows()}
    assert "deploy-digithings-stack-cloudflare.yml" in names
    assert len(names) >= 4, f"only found {sorted(names)}"


@pytest.mark.parametrize(
    ("workflow_name", "spec"),
    _deployable_workflows(),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_every_deploy_workflow_fires_on_push_to_main(
    workflow_name: str, spec: dict[str, Any]
) -> None:
    """Item 3 of DIG-1569, as a standing invariant.

    The audit found one defective workflow. This pins the rule so the defect
    cannot recur silently in a workflow added from the same template.
    """
    if workflow_name in PAGES_GIT_INTEGRATION_WORKFLOWS:
        pytest.skip(
            f"{workflow_name} is a Pages PR build check; production ships from the git integration"
        )
    triggers = _triggers(spec)
    assert "push" in triggers, (
        f"{workflow_name} runs a production deploy command but has no `push` "
        "trigger — a merge deploys nothing (DIG-1569)"
    )
    push = triggers["push"]
    branches = push.get("branches") if isinstance(push, dict) else None
    assert branches is None or "main" in branches, (
        f"{workflow_name} does not trigger on push to main (branches={branches})"
    )


def test_the_pinned_pages_workflows_are_still_build_checks_only() -> None:
    """The allowlist must not rot into a hole.

    Each exempt workflow is exempted because production ships via Cloudflare's
    git integration. If one starts deploying main itself, the exemption is wrong
    and this test fails rather than hiding the regression.
    """
    for name in PAGES_GIT_INTEGRATION_WORKFLOWS:
        path = WORKFLOWS_DIR / name
        assert path.exists(), f"allowlisted workflow {name} no longer exists"
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "push" not in _triggers(spec), (
            f"{name} now triggers on push, so it is no longer a build check — "
            "drop it from PAGES_GIT_INTEGRATION_WORKFLOWS and let the invariant apply"
        )
