"""The stack's merge-to-main deploy lane must keep the merge-to-main deploy
path and Chris's production gate.

Re-derived for `develop` in DIG-4612. The lane was deleted from `develop`
on 2026-10-01 by `f54af7052` (#4919, Human Gate) and DIG-2843 then
decided to "document as-is": the stack ships out-of-band, by hand. Two
things changed after that decision, and they are why this lane exists now:

1. The Container id is no longer a hand-edited string. It is derived from
   the deploying commit (DIG-3229 for this Worker's own id, DIG-3814 for
   the digichat id), so a deploy cannot silently ship the previous
   instance. `npm run deploy` injects the rev, refuses to deploy when the
   commit cannot be resolved, and reads /_stack/meta back afterwards.
2. The lane is re-derived, not reverted (DIG-2843's own precedent).

What this file pins, and why each pin is load-bearing:

* The lane fires on `push: main`. A lane without it deploys nothing on a
  merge (DIG-1569's defect class, and the reason the `production` gate
  went unobservable for ~19 h).
* The deploy job sits behind the `production` environment. That gate is
  what lets Chris stop a deploy; the trigger only makes the gate visible.
* The deploy job waits for `check-deploy-gate`, and that gate job does
  NOT depend on the pull-request-only `check` job. With `needs: [check]`
  the merge-to-main path skipped `check`, so it skipped the gate and then
  skipped `deploy` - DIG-1569 reproduced inside its own fix.
* The deploy runs through the rev-injecting wrapper, never a bare
  `npx wrangler deploy`, which ships the legacy id and cannot guarantee
  eviction.
* The push and pull_request path filters are the same list, and that list
  covers every tree the image bakes in. A merge that changes shipped code
  but matches no filter deploys nothing.
* Every workflow in this repo that can deploy production fires on
  `push: main` (the repo-wide invariant below).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
STACK_WORKFLOW = WORKFLOWS_DIR / "deploy-digithings-stack-cloudflare.yml"

# Paths whose deployment is owned by Cloudflare's git integration, not by a
# workflow here. `gh pages deploy` in these files builds a PR preview;
# production digithings.ai / digiquant.io are built by Cloudflare from main.
PAGES_GIT_INTEGRATION_WORKFLOWS = frozenset(
    {
        "deploy-digithings-cloudflare.yml",
        "deploy-digiquant-cloudflare.yml",
    }
)

# What "this workflow can change production" looks like in practice: a
# shell deploy command in a `run:` step, the wrangler-action composite, or
# this repo's own deploy wrapper (`npm run deploy`, which runs
# `npm exec -- wrangler deploy` with the rev injected).
DEPLOY_COMMAND = re.compile(
    r"(?:npx\s+(?:--no-install\s+)?wrangler\s+deploy|"
    r"wrangler\s+versions\s+deploy|"
    r"gh\s+pages\s+deploy|"
    r"npm\s+run\s+deploy)"
)
WRANGLER_ACTION = "cloudflare/wrangler-action"


def _triggers(spec: dict[str, Any]) -> dict[str, Any]:
    # PyYAML reads the `on:` key as the boolean True.
    raw = spec.get("on")
    if raw is None:
        raw = spec.get(True)
    return raw if isinstance(raw, dict) else {}


def _steps(spec: dict[str, Any], job: str) -> list[dict[str, Any]]:
    jobs = spec.get("jobs") or {}
    entry = jobs.get(job) or {}
    steps = entry.get("steps") or []
    return steps if isinstance(steps, list) else []


def _run_scripts(spec: dict[str, Any], job: str) -> list[str]:
    scripts: list[str] = []
    for step in _steps(spec, job):
        run = step.get("run")
        if isinstance(run, str):
            scripts.append(run)
    return scripts


def _can_deploy(step: dict[str, Any]) -> bool:
    if step.get("uses") == WRANGLER_ACTION:
        with_ = step.get("with") or {}
        return any("deploy" in str(key) for key in with_)
    run = step.get("run")
    if not isinstance(run, str):
        return False
    return bool(DEPLOY_COMMAND.search(run))


def _workflow_files() -> list[Path]:
    return sorted(p for p in WORKFLOWS_DIR.iterdir() if p.suffix in {".yml", ".yaml"})


def _deployable_workflows() -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for path in _workflow_files():
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(spec, dict):
            continue
        jobs = spec.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if isinstance(step, dict) and _can_deploy(step):
                    found.append((path.name, spec))
                    break
            else:
                continue
            break
    return found


def _stack_spec() -> dict[str, Any]:
    return yaml.safe_load(STACK_WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_exists() -> None:
    assert STACK_WORKFLOW.exists(), f"missing {STACK_WORKFLOW}"


def test_it_triggers_on_push_to_main() -> None:
    triggers = _triggers(_stack_spec())
    assert "push" in triggers, (
        "a merge to main must deploy the stack; without `push` the merge "
        "deploys nothing (DIG-1569)"
    )
    assert triggers["push"]["branches"] == ["main"]


def test_it_still_triggers_on_pull_request_and_manual_dispatch() -> None:
    triggers = _triggers(_stack_spec())
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    dispatch = triggers["workflow_dispatch"]
    inputs = dispatch.get("inputs") or {}
    assert "ref" in inputs, (
        "a manual deploy must be able to choose the ref it deploys, so an "
        "operator can ship a promoted tree without a second push"
    )


def test_push_and_pull_request_path_filters_are_identical() -> None:
    triggers = _triggers(_stack_spec())
    assert triggers["push"]["paths"] == triggers["pull_request"]["paths"], (
        "the two path-filter lists drifted: a pull request that validates "
        "different files than the push that deploys them is a lane that "
        "approves one tree and ships another"
    )


def test_the_path_filter_still_covers_the_stack_and_its_deploy_command() -> None:
    paths = set(_triggers(_stack_spec())["push"]["paths"])
    assert "apps/digithings-stack-cloudflare/**" in paths
    assert "infra/docker/Dockerfile.digithings-stack-cloudflare" in paths, (
        "the image this lane builds lives under infra/docker on develop; a "
        "filter that names the old repository-root path matches nothing"
    )
    assert ".github/workflows/deploy-digithings-stack-cloudflare.yml" in paths


def test_the_push_filter_covers_every_tree_the_image_bakes_in() -> None:
    """A merge that changes shipped code must not deploy nothing.

    The deployed image's build context is the repository root, so it copies
    from these trees. A merge touching digikey/** (JWT auth) or
    digisearch/seeds compiled into production and deployed nothing -
    DIG-1569's defect class surviving the fix.
    """
    paths = set(_triggers(_stack_spec())["push"]["paths"])
    for tree in (
        "digibase",
        "digibot",
        "digifetch",
        "digigraph",
        "digikey",
        "digillm",
        "digitrace",
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


def test_a_pull_request_cannot_reach_the_deploy_job() -> None:
    condition = str((_stack_spec()["jobs"]["deploy"] or {}).get("if", ""))
    assert "github.event_name == 'push'" in condition
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert "pull_request" not in condition, (
        "a pull request must validate, never deploy"
    )


def test_deploy_waits_for_its_gate_job() -> None:
    jobs = _stack_spec()["jobs"]
    assert "check-deploy-gate" in jobs["deploy"]["needs"]
    assert jobs["deploy"]["needs"] != ["check"], (
        "with needs: [check] the merge-to-main path skips the pull-request "
        "job, so it skips the gate and then skips the deploy"
    )


def test_the_gate_job_does_not_depend_on_the_pull_request_only_check() -> None:
    jobs = _stack_spec()["jobs"]
    gate_needs = (jobs["check-deploy-gate"] or {}).get("needs") or []
    if isinstance(gate_needs, str):
        gate_needs = [gate_needs]
    for need in gate_needs:
        assert "pull_request" not in str((jobs.get(need) or {}).get("if", "")), need


def test_the_pull_request_check_job_is_scoped_to_pull_requests() -> None:
    condition = str((_stack_spec()["jobs"]["check"] or {}).get("if", ""))
    assert condition == "github.event_name == 'pull_request'"


def test_the_deploy_gate_job_runs_for_both_deploy_events() -> None:
    condition = str(
        (_stack_spec()["jobs"]["check-deploy-gate"] or {}).get("if", "")
    )
    assert condition == "github.event_name != 'pull_request'"


def test_no_validation_job_contains_a_deploy_command() -> None:
    spec = _stack_spec()
    for job in ("check", "check-deploy-gate"):
        for script in _run_scripts(spec, job):
            assert not DEPLOY_COMMAND.search(script), (
                f"{job} must validate, not deploy"
            )


def test_the_deploy_job_checks_out_the_ref_it_will_deploy() -> None:
    steps = _steps(_stack_spec(), "deploy")
    checkout = next((s for s in steps if str(s.get("uses") or "").startswith("actions/checkout")), {})
    assert checkout.get("with", {}).get("ref") == "${{ inputs.ref || github.sha }}"


def test_the_gate_job_checks_out_the_same_ref_as_the_deploy_job() -> None:
    steps = _steps(_stack_spec(), "check-deploy-gate")
    checkout = next((s for s in steps if str(s.get("uses") or "").startswith("actions/checkout")), {})
    assert checkout.get("with", {}).get("ref") == "${{ inputs.ref || github.sha }}"


def test_the_deploy_job_is_still_behind_the_production_environment_gate() -> None:
    assert _stack_spec()["jobs"]["deploy"]["environment"] == "production"


def test_the_concurrency_group_stays_unique_per_run() -> None:
    """A shared group would cancel a deployment Chris already approved.

    The `production` environment can hold a run at the approval gate, so a
    shared group with cancel-in-progress: true cancels the approved run
    and leaves the newer one waiting for a fresh approval. A per-run group
    never queues and never cancels - the same shape, and the same reason,
    as the other production-gated lane in this repo.
    """
    concurrency = _stack_spec().get("concurrency") or {}
    assert isinstance(concurrency, dict), (
        "a scalar concurrency group is refused by the repo's own "
        "environment/concurrency test"
    )
    group = str(concurrency.get("group", ""))
    assert "github.run_id" in group, (
        "the group must be unique per run, or a second merge to main "
        "cancels a deployment that is already approved"
    )


def test_the_deploy_command_and_secrets_are_unchanged() -> None:
    steps = _steps(_stack_spec(), "deploy")
    joined = "\n".join(
        [str(s.get("run") or "") for s in steps]
        + [str(s.get("name") or "") for s in steps]
    )
    assert "npm run deploy --workspace digithings-stack-cloudflare" in joined, (
        "the deploy must go through the rev-injecting wrapper; a bare "
        "`npx wrangler deploy` ships the legacy Container id"
    )
    assert "working-directory" not in joined, (
        "both Containers pin image_build_context = '../..', so the image "
        "build needs the repository root as its context (#4046)"
    )
    deploy_step = next(
        (s for s in steps if "npm run deploy" in str(s.get("run") or "")), {}
    )
    deploy_env = (deploy_step.get("env") or {})
    assert deploy_env["CLOUDFLARE_API_TOKEN"] == (
        "${{ secrets.CLOUDFLARE_API_TOKEN }}"
    ), (
        "wrangler authenticates from the CLOUDFLARE_API_TOKEN environment "
        "variable, and the repo secret of that name is the Workers token this "
        "lane deploys with - the lane was green on it on 2026-10-13 (run "
        "7de39ec9a), and the cron and runner deploy lanes read the same "
        "secret. This lane once read a distinct name, "
        "CLOUDFLARE_WORKERS_API_TOKEN, on the theory that the name is also "
        "the local developer's Vectorize/D1 token (the trap in "
        "apps/digithings-stack-cloudflare/wrangler.toml). No secret of that "
        "name exists, so wrangler was handed an empty token and the deploy "
        "failed on auth (run 39482995993). If a Workers token ever has to "
        "live under a different name, that secret has to be CREATED first - "
        "a name with no secret behind it deploys nothing."
    )
    assert deploy_env["CLOUDFLARE_ACCOUNT_ID"] == (
        "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}"
    )


def test_the_deploy_fails_loudly_when_the_token_is_missing() -> None:
    """An empty secret is a silent deploy, so the lane has to look before it pushes.

    Actions substitutes an empty string for a secret name it cannot resolve, so
    a read of a name nobody defined reached wrangler as an empty token and the
    failure landed on wrangler as an auth error rather than on the missing
    credential. #6013 added the read of `secrets.CLOUDFLARE_WORKERS_API_TOKEN`
    and that secret was never created. This pins the preflight that says so,
    pins that it looks at the credential the deploy actually exports, and pins
    that it never prints the value.
    """
    steps = _steps(_stack_spec(), "deploy")
    preflight = next(
        (s for s in steps if "Preflight" in str(s.get("name") or "")),
        {},
    )
    assert preflight, (
        "the deploy job has no preflight step: an empty CLOUDFLARE_API_TOKEN is "
        "what this lane shipped with, and it only surfaced as a wrangler auth "
        "error (DIG-4717)"
    )
    env = preflight.get("env") or {}
    assert env.get("CLOUDFLARE_API_TOKEN") == (
        "${{ secrets.CLOUDFLARE_API_TOKEN }}"
    ), (
        "the preflight must look at the same name the deploy exports, or it "
        "checks a different credential than the one that runs. "
        "CLOUDFLARE_WORKERS_API_TOKEN is not that name: no secret answers it at "
        "any level, so a preflight on it can never pass (DIG-4717, #6076)"
    )
    script = str(preflight.get("run") or "")
    assert "-z" in script and "exit 1" in script, (
        "the preflight must fail the job when the token is empty"
    )
    assert "::error::" in script, (
        "the preflight must say what is missing on the run page, not just exit 1"
    )
    assert "CLOUDFLARE_API_TOKEN is present" in script, (
        "the success path must say the token is present"
    )
    unguarded = [
        line
        for line in script.splitlines()
        if "$CLOUDFLARE_API_TOKEN" in line and "[" not in line
    ]
    assert not unguarded, (
        f"the preflight expands the token outside a test, which would print it: {unguarded}"
    )


# --- repo-wide invariant: anything that deploys must fire on push: main ---


def test_the_audit_found_at_least_the_workflows_it_should_have() -> None:
    """Guards against the discovery helper silently returning nothing.

    If a future edit breaks the deploy detection, the invariant below
    would pass vacuously. This asserts the fixture set is non-trivial.
    """
    names = {name for name, _ in _deployable_workflows()}
    assert "deploy-digithings-stack-cloudflare.yml" in names
    assert len(names) >= 2, f"only found {sorted(names)}"


@pytest.mark.parametrize(
    ("workflow_name", "spec"),
    _deployable_workflows(),
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_every_deploy_workflow_fires_on_push_to_main(
    workflow_name: str, spec: dict[str, Any]
) -> None:
    """Item 3 of DIG-1569, as a standing invariant.

    The audit found one defective workflow. This pins the rule so the
    defect cannot recur silently in a workflow added from the same
    template.
    """
    if workflow_name in PAGES_GIT_INTEGRATION_WORKFLOWS:
        pytest.skip(
            f"{workflow_name} is a Pages PR build check; production ships "
            "from the git integration"
        )
    triggers = _triggers(spec)
    assert "push" in triggers, (
        f"{workflow_name} runs a production deploy command but has no `push` "
        "trigger - a merge deploys nothing (DIG-1569)"
    )
    push = triggers["push"]
    branches = push.get("branches") if isinstance(push, dict) else None
    assert branches is None or "main" in branches, (
        f"{workflow_name} does not trigger on push to main (branches={branches})"
    )


def test_the_pinned_pages_workflows_are_still_build_checks_only() -> None:
    """The allowlist must not rot into a hole.

    Each exempt workflow is exempted because production ships via
    Cloudflare's git integration. If one starts deploying main itself, the
    exemption is wrong and this test fails rather than hiding the
    regression.
    """
    for name in PAGES_GIT_INTEGRATION_WORKFLOWS:
        path = WORKFLOWS_DIR / name
        assert path.exists(), f"allowlisted workflow {name} no longer exists"
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "push" not in _triggers(spec), (
            f"{name} now triggers on push, so it is no longer a build check - "
            "drop it from PAGES_GIT_INTEGRATION_WORKFLOWS and let the "
            "invariant apply"
        )
