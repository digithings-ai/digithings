"""The Worker build matrix must cover every Worker in the repo, and must keep the
two flags that make the gate credential-free and Docker-free.

`.github/workflows/build-cloudflare-workers.yml` is the only place a Cloudflare
Worker gets a real build before it reaches `develop`. `tsc` cannot see a type-only
import, so a Durable Object class that is only ``import type``d compiles, passes
typecheck, passes every test — and ``wrangler deploy`` then refuses to bundle the
Worker (*depends on the following Durable Objects, which are not exported in your
entrypoint file*). That is finding B1 on PR #5106: 138 tests, a clean typecheck,
and a deploy that would have failed at the moment the branch landed. Before this
workflow the only real build lived inside `deploy-digithings-cron.yml`, i.e.
after merge.

So the gate's value is entirely in its reach. A hard-coded `matrix.app` list
reaches only the apps somebody remembered to type into it: a seventh Worker added
to the repo would ship with no PR-time build, silently, and the failure would
resurface in production exactly as B1 did. So the expected set is **derived**
here — every `apps/*` workspace that ships a `wrangler.toml` *and* pins
`wrangler` in devDependencies — and the matrix is required to equal it in both
directions. Missing entries are the silent-skip case. Stale entries are the other
half and matter just as much: a directory that was renamed or deleted stays in the
matrix, the job fans out a `working-directory:` that does not exist, and the gate
goes red for a reason that has nothing to do with the code.

The derivation is what makes `apps/digithings-web` correct rather than lucky. It
has a `wrangler.toml` and it is absent from the matrix, because it is a Pages
project for a Next.js static export with no `wrangler` dependency of its own
(its own wrangler.toml says so). Pinning wrangler there is the moment it becomes
a Worker this test can build — and at that moment this test goes red and the
matrix has to learn about it.

The two flags are pinned for the same reach-in-reverse reason. Drop
`--containers-rollout=none` and wrangler demands a Docker CLI to build the
container image *"even in dry-run mode"*, so the job fails outright on any
machine without one — three of the six apps are container Workers. Drop
`--dry-run` and the gate starts needing Cloudflare credentials, which breaks it
on fork PRs and puts a secret on the path of a read-only check.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any  # score:allow untyped any — parsed JSON/YAML documents

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-cloudflare-workers.yml"
APPS_DIR = REPO_ROOT / "apps"

pytestmark = pytest.mark.unit


def _workflow() -> dict[str, Any]:
    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _trigger_paths() -> list[str]:
    # PyYAML resolves a bare top-level `on:` key to the boolean True (YAML 1.1), so
    # the trigger block is not reachable under the string "on".
    return _workflow()[True]["pull_request"]["paths"]


def _matrix_apps() -> list[str]:
    return list(_workflow()["jobs"]["build"]["strategy"]["matrix"]["app"])


def _run_blocks() -> list[str]:
    steps = _workflow()["jobs"]["build"]["steps"]
    return [step["run"] for step in steps if isinstance(step.get("run"), str)]


def _buildable_workers() -> set[str]:
    """Every workspace that is a Worker buildable by this gate, derived from the repo.

    A `wrangler.toml` alone is not enough: `apps/digithings-web` is a Pages config
    for a static export and pins no wrangler, so `npm exec -- wrangler` there
    would resolve whatever the registry serves rather than a locked version.
    """
    found = set()
    for manifest_path in sorted(APPS_DIR.glob("*/package.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        app = manifest_path.parent.name
        has_wrangler_config = (manifest_path.parent / "wrangler.toml").is_file()
        pins_wrangler = "wrangler" in manifest.get("devDependencies", {})
        if has_wrangler_config and pins_wrangler:
            found.add(app)
    return found


def test_derivation_is_not_empty() -> None:
    """Guards the derivation itself: an empty set makes every assertion below vacuous.

    If the glob or the key this reads ever stops matching, `test_matrix_covers_every_worker`
    passes on an empty comparison and the gate silently stops being guarded.
    """
    derived = _buildable_workers()
    assert len(derived) >= 6, f"expected the six known Workers, derived {sorted(derived)}"
    # The negative case the derivation exists for. digithings-web has a wrangler.toml
    # and is deliberately not a matrix member; if that ever changes the reason is gone.
    assert "digithings-web" not in derived


def test_matrix_covers_every_worker() -> None:
    """The silent-skip case: a new Worker that nobody typed into the matrix.

    Fails closed on the exact failure this workflow exists to prevent — a Worker
    whose only build runs after merge.
    """
    missing = sorted(_buildable_workers() - set(_matrix_apps()))
    assert not missing, (
        f"apps {missing} ship a wrangler.toml and pin wrangler but are absent from "
        f"{WORKFLOW.name}'s matrix.app — add them there, plus an apps/<app>/** entry "
        f"in its pull_request paths, or a PR touching them gets no Worker build"
    )


def test_matrix_has_no_stale_entries() -> None:
    """The other direction: a renamed or deleted Worker left in the matrix.

    The job would fan out a `working-directory:` that does not exist and go red
    for a reason unrelated to any code, which is how a real failure gets ignored.
    """
    stale = sorted(set(_matrix_apps()) - _buildable_workers())
    assert not stale, f"matrix.app names {stale}, which no longer ship a wrangler.toml + wrangler dep"


@pytest.mark.parametrize("app", sorted(_buildable_workers()))
def test_matrix_app_is_a_real_directory(app: str) -> None:
    assert (APPS_DIR / app / "package.json").is_file(), f"apps/{app} is not a workspace"


@pytest.mark.parametrize("app", sorted(_buildable_workers()))
def test_paths_filter_watches_every_worker(app: str) -> None:
    """A matrix entry whose directory is not in `paths:` never runs.

    The per-app globs are the load-bearing half of the trigger; without one, the
    job is listed but silent on exactly the PRs it was written for.
    """
    paths = _trigger_paths()
    assert f"apps/{app}/**" in paths, f"apps/{app}/** missing from the pull_request paths filter"


@pytest.mark.parametrize("manifest", ["package.json", "package-lock.json"])
def test_paths_filter_watches_the_install_inputs(manifest: str) -> None:
    """`npm ci` resolves the hoisted wrangler, so a lockfile change is a build input.

    Bumping the pinned wrangler in a workspace manifest rewrites the root lock;
    the gate has to fire on that, or the version this job resolves drifts under a
    green tree — the same class of drift as an unpinned linter.
    """
    assert manifest in _trigger_paths()


def test_paths_filter_watches_the_workflow_itself() -> None:
    """Editing the matrix is a build-input change to the gate that reads the matrix."""
    assert f".github/workflows/{WORKFLOW.name}" in _trigger_paths()


@pytest.mark.parametrize(
    "flag",
    [
        # Credential-free: keeps the gate working on fork PRs and keeps a read-only
        # check from needing a secret. Without it the deploy path is authenticated.
        "--dry-run",
        # Docker-free: without it wrangler demands a Docker CLI to build the container
        # image "even in dry-run mode" and the job fails outright where there is none.
        "--containers-rollout=none",
    ],
)
def test_build_keeps_its_flags(flag: str) -> None:
    runs = "\n".join(_run_blocks())
    assert flag in runs, f"{flag} was dropped from the build step"


def test_build_uses_the_pinned_wrangler_not_the_registry() -> None:
    """`npm exec --` resolves the hoisted workspace wrangler; bare `wrangler` would not.

    A bare `npx wrangler` fetches the current release, so the gate would test
    something other than what deploys.
    """
    runs = "\n".join(_run_blocks())
    assert "npm exec -- wrangler" in runs


def test_no_cloudflare_credentials_reach_this_workflow() -> None:
    """`--dry-run` does not authenticate, so no secret belongs here at all.

    Asserted so a future "make it a real deploy" edit cannot quietly add one
    without this test going red and the reason being re-read.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text, "a credential-free build check must not reference secrets.*"
    assert "CLOUDFLARE_API_TOKEN" not in text


def test_no_push_trigger() -> None:
    """push is absent on purpose: the deploy workflows already build on develop.

    A push trigger here would duplicate the real deploy build with no credentials,
    and race the deploy workflows on the same commit.
    """
    triggers = _workflow()[True]
    assert "push" not in triggers, "a push trigger races the deploy workflows and needs credentials"
    assert "workflow_dispatch" in triggers, "the gate must stay manually trippable"


def test_install_is_at_the_repo_root() -> None:
    """The build step sets `working-directory:`; the install step must not.

    The workspaces hoist into the root node_modules, so `npm ci` from inside
    `apps/<app>` installs a different (partial) tree than the one the deploy
    workflows build against.
    """
    steps = _workflow()["jobs"]["build"]["steps"]
    install = [s for s in steps if "npm ci" in str(s.get("run", ""))]
    assert len(install) == 1, "expected exactly one npm ci step"
    assert "working-directory" not in install[0]


def test_build_step_targets_the_matrix_directory() -> None:
    """`working-directory:` is what selects the app; assert it is still interpolated."""
    steps = _workflow()["jobs"]["build"]["steps"]
    build = [s for s in steps if "wrangler deploy" in str(s.get("run", ""))]
    assert len(build) == 1
    assert build[0]["working-directory"] == "apps/${{ matrix.app }}"


def test_paths_filter_never_hardcodes_a_wrangler_toml_app() -> None:
    """`apps/**/wrangler.toml` is the catch-all; a per-app copy is a dead entry.

    The specific per-app globs exist to fire on source edits. Re-deriving the
    config files from them would be redundant, and a second place to forget.
    """
    paths = _trigger_paths()
    for app in _buildable_workers():
        assert f"apps/{app}/wrangler.toml" not in paths
    assert "apps/**/wrangler.toml" in paths
