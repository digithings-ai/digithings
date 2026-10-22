"""The digichat deploy lane needs Chris's approval, and it packages the image
inputs before it builds the image (DIG-5120).

The lane was deleted from `develop` on 2026-10-01 by `f54af7052` (#4919, Human
Gate), together with the stack lane. DIG-4612 ruled on it by name: "Do NOT
restore it with a `push: main` trigger. On main it had NO `production`
environment gate, so a push-triggered successor would deploy production on
every merge with nobody's approval - worse than the manual path. If it comes
back it must be manual dispatch plus a gate."

So this file pins a lane that is:

* MANUAL to deploy - the deploy job's `if` is `workflow_dispatch`, and a merge
  to main runs the validation gate and deploys NOTHING.
* GATED - the deploy job sits behind the `production` environment, whose
  manifest names Chris as the required reviewer.
* RE-DERIVED, not reverted - the deploy goes through the rev-injecting
  wrapper (`npm run deploy`), never a bare `npx wrangler deploy`, which ships
  the legacy pinned Container id (DIG-3814, DIG-4487).
* PACKED - the image this lane builds COPYs a GENERATED, gitignored tree
  (`image-packages/digichat/...`), so every job that leads to the image build
  packages it first, exactly like the stack lane (DIG-4711).

The loops are the point. The Dockerfile's COPY list is checked against the
guard that runs before the build, against the paths the generator writes, and
against the packages the image installs; the workflow's job list is derived
rather than named, so a NEW job that builds the image is covered by the same
assertion that covers the deploy job.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS_DIR / "deploy-digichat-cloudflare-container.yml"
ACTION = REPO_ROOT / ".github" / "actions" / "package-digichat-image-inputs" / "action.yml"
DOCKERFILE = REPO_ROOT / "infra" / "docker" / "Dockerfile.digichat-cloudflare"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
GENERATOR = REPO_ROOT / "scripts" / "package_r5_image_inputs.py"
WRANGLER_TOML = REPO_ROOT / "apps" / "digichat-cloudflare" / "wrangler.toml"
APP_PACKAGE = REPO_ROOT / "apps" / "digichat-cloudflare" / "package.json"

#: The local action that packages the tree. A remote reference would package
#: something else than this repository's Dockerfile asks for.
ACTION_REF = "./.github/actions/package-digichat-image-inputs"

#: The step that makes wrangler build the image. A job that runs it is a job
#: that needs the packaged tree.
DEPLOY_COMMAND = "npm run deploy --workspace digichat-cloudflare"

#: The Worker this lane deploys. It is the `name` in the app's wrangler.toml,
#: and the app's `deploy` script is the rev-injecting wrapper.
WORKER_NAME = "digithings-digichat"


def _doc() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(spec: dict[str, Any]) -> dict[str, Any]:
    # PyYAML reads the `on:` key as the boolean True.
    raw = spec.get("on")
    if raw is None:
        raw = spec.get(True)
    return raw if isinstance(raw, dict) else {}


def _job(spec: dict[str, Any], name: str) -> dict[str, Any]:
    jobs = spec.get("jobs") or {}
    entry = jobs.get(name) or {}
    return entry if isinstance(entry, dict) else {}


def _steps(spec: dict[str, Any], job: str) -> list[dict[str, Any]]:
    steps = _job(spec, job).get("steps") or []
    return steps if isinstance(steps, list) else []


def _run_scripts(spec: dict[str, Any], job: str) -> list[str]:
    scripts: list[str] = []
    for step in _steps(spec, job):
        run = step.get("run")
        if isinstance(run, str):
            scripts.append(run)
    return scripts


def _index_of_ref(job: dict[str, Any], ref: str) -> int:
    """The index of the step that uses ``ref``; -1 when the job has no such step."""
    for index, step in enumerate(job.get("steps") or []):
        if str(step.get("uses", "")) == ref:
            return index
    return -1


def _index_of_run(job: dict[str, Any], needle: str) -> int:
    """The index of the first step whose ``run`` contains ``needle``; -1 when none."""
    for index, step in enumerate(job.get("steps") or []):
        if needle in str(step.get("run", "")):
            return index
    return -1


def _action() -> dict[str, Any]:
    return yaml.safe_load(ACTION.read_text(encoding="utf-8"))


def _action_script() -> str:
    """The packaging step's shell script, comments stripped.

    Comments are stripped so prose that merely names a path cannot satisfy
    the assertions below: the guard has to NAME the path in executable text.
    """
    steps = _action()["runs"]["steps"]
    scripts = [str(step.get("run", "")) for step in steps if "run" in step]
    assert len(scripts) == 1, "the action must have exactly one run step"
    return re.sub(r"#.*$", "", scripts[0], flags=re.M)


def _dockerfile_copy_sources() -> list[str]:
    """Every source the Dockerfile COPYs from the BUILD CONTEXT.

    A `COPY --from=...` line copies from another stage, not from the context,
    so it is not a path the checkout has to carry.
    """
    sources: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("COPY "):
            continue
        tokens = [token for token in line.split()[1:] if not token.startswith("--")]
        if len(tokens) < 2:
            continue
        for source in tokens[:-1]:
            if source.startswith("/"):
                continue
            # `COPY image-packages/digichat/npm/ /tmp/digi-npm/` names the same
            # path as `image-packages/digichat/npm`: the trailing slash is a
            # copy of the directory's contents, not a different path.
            sources.append(source.rstrip("/"))
    return sources


def _dockerfile_image_package_sources() -> list[str]:
    """Every source the Dockerfile COPYs that lives under image-packages/."""
    return [
        source
        for source in _dockerfile_copy_sources()
        if source.startswith("image-packages/")
    ]


def _guarded_paths(script: str) -> set[str]:
    """The paths the action's guard loop actually checks for existence.

    Parsed out of the `for path in ... do` block rather than searched for as
    text: a path that is merely MENTIONED somewhere else in the script must
    not pass for a path the guard checks.
    """
    paths: set[str] = set()
    lines = script.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip().startswith("for path in"):
            index += 1
            while index < len(lines):
                token = lines[index].strip().rstrip("\\").strip()
                if token.startswith("do"):
                    break
                if token:
                    paths.add(token)
                index += 1
        index += 1
    return paths


def _dockerignore_rules() -> list[tuple[str, bool]]:
    rules: list[tuple[str, bool]] = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
        rules.append((line, negated))
    return rules


def _pattern_matches(pattern: str, ancestor: str) -> bool:
    """Whether a .dockerignore pattern matches a path or a directory.

    The model here is deliberately the strict one - it says "excluded" when
    docker would exclude - so a path the guard checks can never read as safe
    because this matcher was more permissive than docker is.
    """
    if "/" not in pattern:
        return fnmatch.fnmatch(ancestor.rsplit("/", 1)[-1], pattern)
    if pattern.startswith("**/"):
        rest = pattern[3:]
        tail = ancestor.split("/")[-1]
        if fnmatch.fnmatch(tail, rest):
            return True
        return fnmatch.fnmatch(ancestor, pattern) or fnmatch.fnmatch(ancestor, "**/" + rest)
    return fnmatch.fnmatch(ancestor, pattern)


def _excluded_by_dockerignore(path: str) -> bool:
    """Whether docker would drop ``path`` from the build context."""
    parts = path.split("/")
    ancestors = ["/".join(parts[: index + 1]) for index in range(len(parts))]
    excluded = False
    for pattern, negated in _dockerignore_rules():
        for ancestor in ancestors:
            if _pattern_matches(pattern, ancestor):
                excluded = not negated
    return excluded


def _load_generator():
    """The packaging script, imported as a module.

    It is imported rather than shelled out to, so the contract between the
    generator and the Dockerfile can be checked against the SAME lists the
    generator writes from.
    """
    spec = importlib.util.spec_from_file_location("package_r5_image_inputs", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _covers(pattern: str, source: str) -> bool:
    """Whether a workflow path filter pattern covers a path.

    GitHub's path filters are globs over the repository root, so `a/**` covers
    `a` and everything under it, and an exact name covers only itself.
    """
    if pattern == source:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[: -len("/**")]
        return source == prefix or source.startswith(prefix + "/")
    return False


def _filter_covers(filters: set[str], source: str) -> bool:
    return any(_covers(pattern, source) for pattern in filters)


# --- the lane's shape ---------------------------------------------------


def test_the_workflow_exists() -> None:
    assert WORKFLOW.exists(), f"missing {WORKFLOW}"


def test_it_triggers_on_push_to_main() -> None:
    triggers = _triggers(_doc())
    assert "push" in triggers, (
        "this repo's own invariant requires every deploy-capable workflow to "
        "fire on a push to main (DIG-1569, tests/scripts/"
        "test_deploy_digithings_stack_cloudflare.py)"
    )
    assert triggers["push"]["branches"] == ["main"]


def test_it_triggers_on_pull_request_and_manual_dispatch() -> None:
    triggers = _triggers(_doc())
    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    inputs = (triggers["workflow_dispatch"] or {}).get("inputs") or {}
    assert "ref" in inputs, (
        "a manual deploy must be able to choose the ref it deploys, so an "
        "operator can ship a promoted tree without a second push"
    )
    assert inputs["ref"].get("default") == "main", (
        "main is the only branch the production environment's branch policy "
        "allows a deployment to run on"
    )


def test_push_and_pull_request_path_filters_are_identical() -> None:
    triggers = _triggers(_doc())
    assert triggers["push"]["paths"] == triggers["pull_request"]["paths"], (
        "the two path-filter lists drifted: a pull request that validates "
        "different files than the push that validates them is a lane that "
        "approves one tree and ships another"
    )


def test_the_path_filter_covers_the_worker_and_its_deploy_command() -> None:
    paths = set(_triggers(_doc())["push"]["paths"])
    assert "apps/digichat-cloudflare/**" in paths
    assert "infra/docker/Dockerfile.digichat-cloudflare" in paths, (
        "the image this lane builds lives under infra/docker on develop; a "
        "filter that names the old repository-root path matches nothing"
    )
    assert ".github/workflows/deploy-digichat-cloudflare-container.yml" in paths


def test_the_path_filter_covers_every_tree_the_image_bakes_in() -> None:
    """A merge that changes shipped code must not deploy nothing.

    The deployed image's build context is the repository root, so it copies
    from these paths, and the packaged npm workspaces are built from their own
    trees. The list is derived from the Dockerfile and from the generator, so
    a new COPY fails here instead of shipping an image that misses it.
    """
    filters = set(_triggers(_doc())["push"]["paths"])
    module = _load_generator()
    sources = [
        source
        for source in _dockerfile_copy_sources()
        if not source.startswith("image-packages/")
    ]
    for source in sources:
        assert _filter_covers(filters, source), (
            f"{source} is copied into the deployed image but a push to main "
            "changing it matches no path filter, so the merge deploys nothing"
        )
    for relative in module.npm_input_paths().values():
        tree = relative.relative_to(REPO_ROOT).as_posix()
        assert _filter_covers(filters, tree), (
            f"{tree} is packaged into the deployed image (the generator "
            "fingerprints it) but matches no path filter, so a merge that "
            "changes it deploys nothing"
        )


def test_the_path_filters_include_the_packaging_action() -> None:
    """The action decides what the image carries, so a change to it must run the lane.

    So is .dockerignore: the image is built from the repository root, so the
    root .dockerignore decides what the build context carries. A merge that
    only edits it changes the image and matches no filter.
    """
    triggers = _triggers(_doc())
    for trigger in ("push", "pull_request"):
        paths = set(triggers[trigger]["paths"])
        assert ".github/actions/package-digichat-image-inputs/action.yml" in paths, (
            f"the {trigger} path filter does not match the packaging action, so a "
            "change to it is never proven in CI and the merge deploys the "
            "previous recipe"
        )
        assert ".dockerignore" in paths, (
            f"the {trigger} path filter does not match .dockerignore, so a merge "
            "that only edits it changes what the build context carries and "
            "matches no filter"
        )
        assert _filter_covers(paths, "scripts/package_r5_image_inputs.py"), (
            f"the {trigger} path filter does not match the packaging generator, "
            "so a change to it matches no filter and the merge packages the "
            "previous recipe"
        )


# --- the deploy is manual, gated, and never reachable from a pull request ---


def test_the_deploy_job_is_manual_dispatch_only() -> None:
    """The rule DIG-4612 ruled on by name, for this file.

    A push-triggered deploy would put production behind nobody's approval:
    the old lane had no `production` environment gate at all, which is why it
    was deleted.
    """
    condition = str(_job(_doc(), "deploy").get("if", ""))
    assert condition == "github.event_name == 'workflow_dispatch'", (
        "the deploy job must run on a manual dispatch only: a push-triggered "
        "deploy would ship production without Chris's approval (DIG-4612)"
    )
    assert "pull_request" not in condition
    assert "push" not in condition


def test_no_validation_job_contains_a_deploy_command() -> None:
    spec = _doc()
    for job in ("check", "check-deploy-gate"):
        for script in _run_scripts(spec, job):
            assert "wrangler deploy" not in script, f"{job} must validate, not deploy"


def test_the_deploy_job_is_behind_the_production_environment_gate() -> None:
    assert _job(_doc(), "deploy").get("environment") == "production", (
        "the production environment names Chris as the required reviewer; "
        "without it the deploy would ship on nobody's approval"
    )


def test_the_deploy_waits_for_its_gate_job() -> None:
    jobs = _doc()["jobs"]
    assert "check-deploy-gate" in jobs["deploy"]["needs"]
    assert jobs["deploy"]["needs"] != ["check"], (
        "with needs: [check] the dispatch path would skip the pull-request "
        "job, so it would skip the gate and then skip the deploy"
    )


def test_the_gate_job_does_not_depend_on_the_pull_request_only_check() -> None:
    jobs = _doc()["jobs"]
    gate_needs = (jobs["check-deploy-gate"] or {}).get("needs") or []
    if isinstance(gate_needs, str):
        gate_needs = [gate_needs]
    for need in gate_needs:
        assert "pull_request" not in str((jobs.get(need) or {}).get("if", "")), need


def test_the_pull_request_check_job_is_scoped_to_pull_requests() -> None:
    condition = str(_job(_doc(), "check").get("if", ""))
    assert condition == "github.event_name == 'pull_request'"


def test_the_deploy_gate_job_runs_for_both_deploy_events() -> None:
    condition = str(_job(_doc(), "check-deploy-gate").get("if", ""))
    assert condition == "github.event_name != 'pull_request'", (
        "the gate must run on a push to main and on a dispatch, or a merge "
        "proves nothing and a dispatch skips the proof"
    )


def test_the_deploy_job_checks_out_the_ref_it_will_deploy() -> None:
    steps = _steps(_doc(), "deploy")
    checkout = next(
        (s for s in steps if str(s.get("uses") or "").startswith("actions/checkout")), {}
    )
    assert checkout.get("with", {}).get("ref") == "${{ inputs.ref || github.sha }}"


def test_the_gate_job_checks_out_the_same_ref_as_the_deploy_job() -> None:
    steps = _steps(_doc(), "check-deploy-gate")
    checkout = next(
        (s for s in steps if str(s.get("uses") or "").startswith("actions/checkout")), {}
    )
    assert checkout.get("with", {}).get("ref") == "${{ inputs.ref || github.sha }}"


def test_the_concurrency_group_stays_unique_per_run() -> None:
    """A shared group would cancel a deployment Chris already approved.

    The `production` environment can hold a run at the approval gate, so a
    shared group with cancel-in-progress: true cancels the approved run and
    leaves the newer one waiting for a fresh approval.
    """
    concurrency = _doc().get("concurrency") or {}
    assert isinstance(concurrency, dict), (
        "a scalar concurrency group is refused by the repo's own "
        "environment/concurrency test"
    )
    group = str(concurrency.get("group", ""))
    assert "github.run_id" in group, (
        "the group must be unique per run, or a second dispatch cancels a "
        "deployment that is already approved"
    )


# --- the deploy command, the credentials and the preflight ---------------


def test_the_deploy_runs_the_worker_the_wrangler_config_names() -> None:
    """The lane deploys `digithings-digichat`, and the app's own deploy script.

    The Worker name is the `name` field of the app's wrangler.toml; the
    wrapper (`apps/digichat-cloudflare/scripts/deploy.mjs`) runs wrangler from
    that app's directory, so that is the config it uses.
    """
    toml = WRANGLER_TOML.read_text(encoding="utf-8")
    match = re.search(r'^name\s*=\s*"([^"]+)"', toml, flags=re.M)
    assert match, "the app's wrangler.toml names no Worker"
    assert match.group(1) == WORKER_NAME
    package = json.loads(APP_PACKAGE.read_text(encoding="utf-8"))
    assert package["scripts"]["deploy"] == "node scripts/deploy.mjs", (
        "the deploy must go through the rev-injecting wrapper"
    )


def test_the_deploy_command_and_secrets_are_unchanged() -> None:
    steps = _steps(_doc(), "deploy")
    joined = "\n".join(
        [str(s.get("run") or "") for s in steps]
        + [str(s.get("name") or "") for s in steps]
    )
    assert DEPLOY_COMMAND in joined, (
        "the deploy must go through the rev-injecting wrapper; a bare "
        "`npx wrangler deploy` ships the legacy Container id (DIG-3814, "
        "DIG-4487)"
    )
    assert "npx wrangler deploy" not in joined, (
        "a bare `npx wrangler deploy` ships the legacy pinned Container id"
    )
    assert "working-directory" not in joined, (
        "the Container pins image_build_context = '../..', so the image build "
        "needs the repository root as its context (#4046)"
    )
    deploy_step = next(
        (s for s in steps if "npm run deploy" in str(s.get("run") or "")), {}
    )
    deploy_env = deploy_step.get("env") or {}
    assert deploy_env["CLOUDFLARE_API_TOKEN"] == (
        "${{ secrets.CLOUDFLARE_API_TOKEN }}"
    ), (
        "wrangler authenticates from the CLOUDFLARE_API_TOKEN environment "
        "variable, and the repo secret of that name is the Workers token this "
        "lane deploys with. A name with no secret behind it deploys nothing."
    )
    assert deploy_env["CLOUDFLARE_ACCOUNT_ID"] == (
        "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}"
    )


def test_the_deploy_fails_loudly_when_the_token_is_missing() -> None:
    """An empty secret is a silent deploy, so the lane has to look before it pushes.

    Actions substitutes an empty string for a secret name it cannot resolve, so
    a read of a name nobody defined reached wrangler as an empty token and the
    failure landed on wrangler as an auth error rather than on the missing
    credential. This pins the preflight that says so, pins that it looks at
    the credential the deploy actually exports, and pins that it never prints
    the value.
    """
    steps = _steps(_doc(), "deploy")
    preflight = next(
        (s for s in steps if "Preflight" in str(s.get("name") or "") and "token" in str(s.get("name") or "")),
        {},
    )
    assert preflight, (
        "the deploy job has no token preflight: an empty CLOUDFLARE_API_TOKEN "
        "is what the sibling lane shipped with, and it only surfaced as a "
        "wrangler auth error (DIG-4717)"
    )
    env = preflight.get("env") or {}
    assert env.get("CLOUDFLARE_API_TOKEN") == "${{ secrets.CLOUDFLARE_API_TOKEN }}"
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


def test_the_deploy_says_which_ref_and_rev_it_ships() -> None:
    """The approval is about a ref and a rev, so the run must say both.

    The Container id is derived from the deployed commit (DIG-3814), and the
    wrapper refuses to deploy when the commit cannot be resolved. A dispatch
    at a ref that does not resolve must fail BEFORE the production gate, not
    after Chris approved it.
    """
    steps = _steps(_doc(), "deploy")
    preflight = next(
        (s for s in steps if "rev" in str(s.get("name") or "").lower()),
        {},
    )
    assert preflight, "the deploy job does not say which ref and rev it ships"
    script = str(preflight.get("run") or "")
    assert "git rev-parse --verify HEAD" in script, (
        "the preflight must resolve the commit the deploy would ship"
    )
    assert "exit 1" in script and "::error::" in script, (
        "the preflight must fail the job when the ref does not resolve"
    )


def test_the_lane_never_mentions_a_secret_name_that_does_not_exist() -> None:
    """CLOUDFLARE_WORKERS_API_TOKEN is not a secret name in this repo.

    It broke the sibling lane: no secret answered it, so wrangler was handed
    an empty token and the deploy failed on auth (run 39482995993).
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    assert "CLOUDFLARE_WORKERS_API_TOKEN" not in code, (
        "the deploy reads a secret name that does not exist"
    )


# --- the image inputs ----------------------------------------------------


def test_the_deploy_job_packages_before_it_deploys() -> None:
    """The build context has to carry image-packages/ when the image is built."""
    job = _job(_doc(), "deploy")
    packaging = _index_of_ref(job, ACTION_REF)
    assert packaging != -1, f"the deploy job does not use {ACTION_REF}"
    deploy = _index_of_run(job, DEPLOY_COMMAND)
    assert deploy != -1, "the deploy job does not deploy the digichat Worker"
    assert packaging < deploy, "the deploy job must package the image inputs before it deploys"


def test_the_deploy_gate_packages_too() -> None:
    """The gate is the last job before the production approval, so it proves the packaging."""
    job = _job(_doc(), "check-deploy-gate")
    assert _index_of_ref(job, ACTION_REF) != -1, (
        f"the deploy gate does not use {ACTION_REF}: a broken generator would then be "
        "discovered at a deploy Chris already approved"
    )


def test_the_pull_request_check_packages_too() -> None:
    """The generator is proven in CI before a change can reach main."""
    job = _job(_doc(), "check")
    assert _index_of_ref(job, ACTION_REF) != -1, (
        f"the pull-request check does not use {ACTION_REF}: the generator would first "
        "be exercised at a production deploy"
    )


def test_every_job_that_builds_the_image_packages_it_first() -> None:
    """The job list is DERIVED, so a new build job is covered by the same rule.

    Naming the three jobs would let a fourth one - a dry-run lane, a second
    deploy job - build the image out of a context with no packaged tree, and
    every test here would stay green.
    """
    jobs = _doc()["jobs"]
    builders = {
        name: job
        for name, job in jobs.items()
        if _index_of_run(job, DEPLOY_COMMAND) != -1
    }
    assert builders, "the workflow no longer builds the image - has the lane changed?"
    for name, job in builders.items():
        packaging = _index_of_ref(job, ACTION_REF)
        deploy = _index_of_run(job, DEPLOY_COMMAND)
        assert packaging != -1, (
            f"the {name} job builds the image but does not use {ACTION_REF}, so its "
            "build context carries no packaged tree"
        )
        assert packaging < deploy, f"the {name} job must package the image inputs before it builds"


def test_the_action_runs_the_npm_scope_of_the_generator() -> None:
    """The scope is this image's, and it is named.

    The full generator also builds the stack image's wheels - a fresh,
    unpinned `uv lock` against PyPI - and the runner payload, which the
    digichat image installs neither. A production deploy must not inherit a
    network-dependent resolution step it does not use.
    """
    script = _action_script()
    assert "python3 scripts/package_r5_image_inputs.py --npm-only" in script, (
        "the action does not package the digichat image's inputs"
    )
    assert "--stack-only" not in script, (
        "--stack-only packages the stack image's inputs, not this image's"
    )
    for line in script.splitlines():
        if "package_r5_image_inputs.py" in line and not re.search(
            r"package_r5_image_inputs\.py\s+--", line
        ):
            pytest.fail(
                "the action runs the FULL generator, which builds the stack "
                "wheels and the runner payload the digichat image does not "
                f"install: {line.strip()}"
            )
    assert "python3 scripts/package_r5_image_inputs.py --check-only --npm-only" in script, (
        "the action does not verify the tree it just packaged"
    )


def test_the_action_sets_up_the_toolchain_the_generator_needs() -> None:
    """The npm scope packs with node and copies with python; it needs no uv."""
    steps = _action()["runs"]["steps"]
    uses = [str(step.get("uses", "")) for step in steps]
    assert any(u.startswith("actions/setup-node") for u in uses), (
        "the generator packs the npm workspaces with `npm pack`, so it needs node"
    )
    assert any(u.startswith("actions/setup-python") for u in uses), (
        "the generator is a python script, so it needs python"
    )
    assert not any(u.startswith("astral-sh/setup-uv") for u in uses), (
        "the npm scope installs no wheel, so it needs no uv"
    )


def test_the_guard_covers_every_path_the_dockerfile_copies() -> None:
    """A new COPY under image-packages/ without a matching guard fails here."""
    script = _action_script()
    sources = _dockerfile_image_package_sources()
    assert sources, "the Dockerfile copies nothing under image-packages/: has the image changed?"
    guarded = _guarded_paths(script)
    assert guarded, "the action's guard checks no path at all"
    for source in sources:
        assert source in guarded, (
            f"the Dockerfile COPYs {source} but the packaging guard does not check it, "
            "so a missing path would not fail the step"
        )
    assert "::error::" in script, "the guard does not report what is missing"
    assert re.search(r"exit\s+(?:1|\"?\$\{?missing)", script), (
        "the guard reports a missing path but never exits non-zero, so the step would "
        "report success and the build would still die on the same missing path"
    )


def test_the_generator_writes_every_path_the_dockerfile_copies() -> None:
    """The other half of the loop: the guard checks what the generator writes.

    A rename of a generator output would leave the Dockerfile and the guard
    naming the old path, and only the deploy job would notice - after Chris's
    production approval.
    """
    module = _load_generator()
    written = {"image-packages/digichat/npm"}
    written |= {
        f"image-packages/digichat/manifests/{key}/package.json"
        for key in module.NPM_MANIFESTS
    }
    assert set(_dockerfile_image_package_sources()) == written, (
        "the Dockerfile COPYs a path the npm scope does not write, or the npm "
        "scope writes a path the Dockerfile never reads"
    )


def test_the_guard_expects_the_tarballs_the_image_unpacks() -> None:
    """A partial tarball set is a partial image, so the guard counts them."""
    module = _load_generator()
    expected = len(module.NPM_PACKAGES)
    script = _action_script()
    match = re.search(r'!= "(\d+)"', script)
    assert match, "the guard does not check how many tarballs the tree holds"
    assert int(match.group(1)) == expected, (
        f"the guard expects {match.group(1)} tarball(s) but the image installs "
        f"{expected}"
    )


def test_the_packaged_paths_survive_the_dockerignore_filter() -> None:
    """The guard reads the FILESYSTEM; docker reads the FILTERED context.

    A `.dockerignore` basename rule (`data`, `tests`, `dist`, `scripts`)
    matches at any depth, so a subdirectory named `data` would be dropped
    silently: the COPY still succeeds and the image ships an empty tree.
    """
    for source in _dockerfile_image_package_sources():
        assert not _excluded_by_dockerignore(source), (
            f".dockerignore drops {source} from the build context, so the image would "
            "carry no such path even though the guard passed"
        )
    for source in _dockerfile_copy_sources():
        if source.startswith("image-packages/"):
            continue
        assert not _excluded_by_dockerignore(source), (
            f".dockerignore drops {source} from the build context, so the image "
            "would carry no such path even though the guard passed"
        )
