"""The digichat publish lane stays build-only, and stays bound to the tag (DIG-1242 / DIG-1294).

DIG-1242 deleted ``publish-digichat-image.yml`` in the strict-essentials cut
(``f54af7052``, #4919). Restoring it looked like a `git show f54af7052^:...`
away, which is exactly the trap: the restored file would have carried two
properties that DIG-1242 exists to end, and both read as reasonable in review.

*The ``push: branches: [main]`` backstop breaks the binding.* The tag is the
release moment, so the tag push is the only trigger that can produce a bound
image — it names a version and resolves to exactly one commit. A main-push build
publishes ``v2.4.0`` labelled with main's commit; the idempotency guard then
skips the tag build; and the release tag ends up naming a commit no published
image was built from. The safety net re-opens the image→commit hole.

*An ACA promotion in the same file would be a different lane.* The promotion
target belongs to DataTap, not to us: ``digithings`` holds no Azure credential,
and adding one is a security decision with an owner and a rotation path
(DIG-1349), not an improvement to a build workflow. The tag-push publish lane
can hold ``packages: write`` — GHCR is ours. It must hold nothing that could
reach a customer Container App.

These are asserted structurally, over the workflow's own document, because both
properties are invisible to ``actionlint`` and to every other test in this
directory: a branch trigger or an ``azure/login`` step is valid YAML that lints
clean and would still ship. The assertions are about the *shape* of the lane, so
they survive a rewrite of its steps.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-digichat-image.yml"

#: The tag pattern the lane publishes from, and the same shape as ``TAG_RE`` in
#: ``scripts/check_digichat_image_binding.py``.
TAG_GLOB = "digichat-v*"
TAG_RE = r"^digichat-v[0-9]+\.[0-9]+\.[0-9]+$"


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    """``on:`` — YAML 1.1 parses a bare ``on`` key as the boolean ``True``."""
    raw = doc.get("on", doc.get(True))
    assert isinstance(raw, dict), "workflow has no trigger mapping"
    return raw


def _job(doc: dict) -> dict:
    jobs = doc["jobs"]
    assert len(jobs) == 1, "the lane must stay a single job"
    return next(iter(jobs.values()))


def _steps(doc: dict) -> list[dict]:
    return _job(doc)["steps"]


def _run_scripts(doc: dict) -> str:
    return "\n".join(step["run"] for step in _steps(doc) if "run" in step)


def _no_comments(script: str) -> str:
    """Strip ``#`` to end of line, so prose in a comment block cannot satisfy an assertion.

    Every guard in this file is asserted on text. Without this, moving a guard
    into the comment block above it leaves the tests green and the lane
    unguarded — which is exactly the failure a reader would not notice.
    """
    return re.sub(r"#.*$", "", script, flags=re.M)


def _guards(doc: dict) -> str:
    """The lane's executable text: ``run`` blocks with their comments removed."""
    return _no_comments(_run_scripts(doc))


def _structure(doc: dict) -> str:
    """The whole parsed workflow, re-serialised — every key, comments dropped.

    Needed because a hand-picked subset of nodes (only ``uses``, only ``run``)
    cannot see a credential arriving through ``with:``, ``env:``, a job-level
    ``permissions:`` block, or a job-level ``environment:``.
    """
    return yaml.safe_dump(doc)


def _build_step(doc: dict) -> dict:
    """The single ``docker/build-push-action`` step — the lane's only image producer."""
    steps = [
        step for step in _steps(doc) if str(step.get("uses", "")).startswith("docker/build-push")
    ]
    assert len(steps) == 1, "expected exactly one build step"
    return steps[0]


def test_lane_exists_with_the_documented_name() -> None:
    assert WORKFLOW.is_file(), (
        f"{WORKFLOW.name} is missing — without it a digichat release tag publishes "
        "no image anywhere, which is the hole DIG-1242 was raised for"
    )
    assert _doc()["name"] == "Publish: digichat image"


def test_a_release_tag_is_the_only_automatic_trigger() -> None:
    """No branch trigger: a tag names a version and one commit; a branch does neither."""
    on = _triggers(_doc())
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": [TAG_GLOB]}


def test_no_schedule() -> None:
    """develop carries zero ``on.schedule`` keys (tests/scripts/test_no_gha_schedules.py)."""
    assert "schedule" not in _triggers(_doc())


def test_the_lane_cannot_reach_azure() -> None:
    """No cloud credential of any kind — the promotion stays a human step.

    Scanned over the re-serialised document rather than a hand-picked set of
    nodes. The widenings that matter all arrive through keys a ``uses``+``run``
    concatenation cannot see: a step ``env:``, a ``with:``, a job-level
    ``permissions:`` block, a job-level ``environment:``.
    """
    structure = _structure(_doc())
    job = _job(_doc())

    # A stored secret of any kind other than the automatic GITHUB_TOKEN.
    assert not re.search(r"secrets\.(?!GITHUB_TOKEN\b)", structure), (
        "the only secret this lane may read is the automatic GITHUB_TOKEN"
    )
    # An OIDC token is the other route to a cloud identity.
    assert "id-token" not in structure, "id-token: write would mint an Azure token"
    # No environment gate: there is no approval path to a write, and the
    # queueing-concurrency invariant in
    # tests/scripts/test_workflow_environment_concurrency.py has nothing to say.
    assert "environment" not in job, "an environment gate implies an approvable write"
    # Belt and braces on the two spellings of an ACA promotion.
    assert "azure/login" not in structure, "an ACA promotion is lane B, not this lane"
    assert not re.search(r"\baz\b", _guards(_doc())), (
        "no az CLI invocation in a lane that cannot reach Azure"
    )
    assert "containerapp" not in _guards(_doc()).lower()


def test_permissions_are_the_minimum() -> None:
    """``contents: read`` to check out, ``packages: write`` to push to GHCR. Nothing else."""
    assert _doc()["permissions"] == {"contents": "read", "packages": "write"}


def test_publishes_are_queued_not_cancelled() -> None:
    """A publish halfway through a push must not be killed by a second run of the tag."""
    concurrency = _doc()["concurrency"]
    assert concurrency["group"] == "publish-digichat-image"
    assert concurrency["cancel-in-progress"] is False


def test_the_image_is_built_from_the_repo_root() -> None:
    """digichat is an npm workspace member; ``apps/digichat`` is not a build context."""
    with_ = _build_step(_doc())["with"]
    assert with_["context"] == "."
    assert with_["file"] == "apps/digichat/Dockerfile"
    assert with_["push"] is True


def test_the_build_names_its_own_commit() -> None:
    """Without ``DIGICHAT_REVISION`` the image carries no revision and the binding check fails."""
    with_ = _build_step(_doc())["with"]
    build_args = with_["build-args"]
    revision_arg = re.search(r"^DIGICHAT_REVISION=(.*)$", build_args, re.M)
    assert revision_arg is not None, "DIGICHAT_REVISION must be passed to the build"
    assert revision_arg.group(1) == "${{ steps.version.outputs.commit }}", (
        "DIGICHAT_REVISION must come from the resolved tag commit, not from github.sha — "
        "on a workflow_dispatch those differ"
    )
    assert re.search(r"^DIGICHAT_VERSION=", build_args, re.M)
    # One tag per line: splitting on whitespace would tear `${{ … }}` apart.
    tags = [line.strip() for line in with_["tags"].splitlines() if line.strip()]
    assert tags == [
        "ghcr.io/digithings-ai/digichat:v${{ steps.version.outputs.version }}",
        "ghcr.io/digithings-ai/digichat:latest",
    ]


def test_the_tag_must_resolve_to_a_commit() -> None:
    """Nothing to bind against means the image proves only that *something* built it."""
    # Comment-stripped: a guard that only survives inside a comment is not a guard.
    guards = _guards(_doc())
    assert 'git rev-list -n1 "$tag"' in guards
    assert "does not resolve to a commit" in guards
    # `set -e` would abort on git's own error before the diagnostic could print,
    # so the lookup must tolerate a bad ref. Without this the guard is dead code.
    resolve = re.search(r"git rev-list -n1 \"\$tag\"[^\n]*", guards)
    assert resolve is not None and "|| true" in resolve.group(0), (
        "the rev-list lookup must tolerate failure so the emptiness check is reachable"
    )


def test_the_tag_version_must_match_package_json() -> None:
    """The drift the deleted workflow refused to publish; kept."""
    guards = _guards(_doc())
    assert "jq -r .version apps/digichat/package.json" in guards
    assert "does not match apps/digichat/package.json" in guards
    # Same shape as the checker's TAG_RE, so the lane and the checker cannot
    # disagree about what a release tag is.
    assert re.search(r"\^digichat-v\[0-9\]\+\\\.\[0-9\]\+\\\.\[0-9\]\+\$", guards)


def test_publishing_an_existing_version_is_a_no_op() -> None:
    """Release tags are immutable here: re-pushing one would change the digest under its name."""
    doc = _doc()
    runs = _run_scripts(doc)
    assert 'docker manifest inspect "$IMAGE_TAG"' in runs
    assert "already published" in runs
    # No force, no re-tag: the escape is a new patch version.
    assert "force" not in _triggers(doc)["workflow_dispatch"]["inputs"]

    # The manifest check is only a guard if something reads its output. Without
    # this the check computes `exists` and the build pushes regardless, so a
    # re-dispatch of an already-released tag would change the digest under it.
    steps = _steps(doc)
    check = next((s for s in steps if s.get("id") == "check"), None)
    assert check is not None, "the manifest check needs an id for the build step to gate on"
    build = _build_step(doc)
    assert build.get("if") == "steps.check.outputs.exists == 'false'", (
        "the build must be gated on the check confirming the tag is not published; "
        f"got if={build.get('if')!r}"
    )
    # Both outcomes must be consumed, or the "already published" branch is dead.
    conditions = [s.get("if") for s in steps if s.get("if")]
    assert any("exists == 'true'" in c for c in conditions), (
        "no step reports the already-published case"
    )
    # And the check must distinguish absent from unaskable — collapsing both
    # into exists=false would repush over a released tag during a registry blip.
    check_guards = _no_comments(check["run"])
    assert "manifest unknown" in check_guards, (
        "the check must key absent off the registry's own answer, not off any failure"
    )
    assert "set -euo pipefail" in check_guards


def test_the_lane_proves_its_own_output() -> None:
    """A Dockerfile that stops emitting the revision must fail here, not at the next promotion."""
    guards = _guards(_doc())
    assert "scripts/check_digichat_image_binding.py --facts -" in guards
    assert "org.opencontainers.image.revision" in guards
    # `--format` everywhere: a bare `docker inspect` emits a JSON array, which
    # the checker rejects as bad input (runbook §2). Matched per line — a `.`
    # that does not cross newlines would let the lookahead see only the tail of
    # one line and pass.
    inspect_lines = [line for line in guards.splitlines() if "docker inspect" in line]
    assert inspect_lines, "the verification step must inspect the image it pushed"
    for line in inspect_lines:
        assert "--format" in line, f"docker inspect without --format: {line.strip()!r}"


def test_the_checkout_can_resolve_the_tag() -> None:
    """A shallow clone of a tag has no history, so ``git rev-list -n1`` cannot bind it."""
    checkout = next(
        step for step in _steps(_doc()) if step.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["ref"] == "${{ inputs.tag || github.ref }}"
