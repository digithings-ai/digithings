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


def _step_by_id(doc: dict, step_id: str) -> dict:
    step = next((s for s in _steps(doc) if s.get("id") == step_id), None)
    assert step is not None, f"no step with id {step_id!r}"
    return step


def _refuses(guards: str, marker: str) -> bool:
    """True when the diagnostic ``marker`` is followed within a few lines by ``exit 1``.

    A refusal that prints an error and keeps going is not a refusal. Asserting
    only that the message exists is the trap this closes: a comment naming the
    failure satisfies a substring check, and so does a diagnostic with no exit
    behind it — in which case the step reports success and the push runs.
    """
    lines = guards.splitlines()
    for index, line in enumerate(lines):
        if marker in line:
            if re.search(r"^\s*exit 1\s*$", "\n".join(lines[index : index + 3]), re.M):
                return True
    return False


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
    """digichat is an npm workspace member; ``apps/digichat`` is not a build context.

    ``push: false`` is the design, not a regression. The image is loaded into the
    runner so the boot probe can start it, and a separate step pushes only after
    the probe has watched it serve. A build step that pushes publishes an image
    nobody has booted.
    """
    with_ = _build_step(_doc())["with"]
    assert with_["context"] == "."
    assert with_["file"] == "apps/digichat/Dockerfile"
    assert with_["push"] is False, "the build step must not push; the probed push step does"
    assert with_["load"] is True, "the image must be in the runner's daemon for the probe to boot"


def test_the_build_names_its_own_commit() -> None:
    """Without ``DIGICHAT_REVISION`` the image carries no revision and the binding check fails."""
    with_ = _build_step(_doc())["with"]
    build_args = with_["build-args"]
    revision_arg = re.search(r"^DIGICHAT_REVISION=(.*)$", build_args, re.M)
    assert revision_arg is not None, "DIGICHAT_REVISION must be passed to the build"
    assert revision_arg.group(1) == "${{ steps.version.outputs.commit }}", (
        "DIGICHAT_REVISION must come from the resolved commit, not from github.sha — "
        "on a workflow_dispatch those differ"
    )
    assert re.search(r"^DIGICHAT_VERSION=", build_args, re.M)
    # The names are decided once, in the resolve step, and handed over whole.
    # A step output is one line, so no consumer can tear a `${{ … }}` apart
    # the way an inline multi-line tag list can.
    assert with_["tags"] == "${{ steps.version.outputs.tags }}"


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


def test_the_published_check_probes_the_name_the_build_actually_publishes() -> None:
    """The idempotency guard must ask about the name this run will publish.

    On the release path the two agree (`:vX.Y.Z`). On the ref path they do not:
    the build publishes `:sha-<commit>`. If the guard rebuilt the release name
    from the version, a rehearsal dispatched after that version was released
    would read `exists=true` and skip the build it was dispatched to make.
    """
    doc = _doc()
    check = _step_by_id(doc, "check")
    assert check["env"]["IMAGE_TAG"] == "${{ steps.version.outputs.image }}", (
        "the check step must probe the resolve step's own image name, not one "
        "reconstructed from the version"
    )

    # Discriminates rather than restating: the resolve step emits two different
    # names on the two paths, so a single literal could never satisfy both.
    guards = _no_comments(_step_by_id(doc, "version")["run"])
    assert 'image="${image_repo}:v${version}"' in guards
    assert 'image="${image_repo}:sha-$(git rev-parse --short=12 HEAD)"' in guards


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
    """A shallow clone of a tag has no history, so ``git rev-list -n1`` cannot bind it.

    ``inputs.ref`` is in the chain for the same reason: a rehearsal build checks
    out a branch, and the resolve step still needs the tree at that ref.
    """
    checkout = next(
        step for step in _steps(_doc()) if step.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["ref"] == "${{ inputs.tag || inputs.ref || github.ref }}"


def test_a_rehearsal_image_can_be_requested_without_a_release_tag() -> None:
    """The runbook's Step 1 rehearsal needs an artifact before ``digichat-v2.4.0`` exists.

    That tag does not exist, and cutting it is a release decision, not a deploy
    step. Without a ref input the rehearsal step has nothing to promote, so the
    lane would only ever produce images for releases that already shipped.
    """
    inputs = _triggers(_doc())["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"tag", "ref"}
    assert inputs["tag"]["required"] is False, "tag must be optional, or a ref build is unreachable"
    assert inputs["ref"]["required"] is False, "ref must be optional, or a tag build is unreachable"
    assert inputs["ref"]["type"] == "string"


def test_tag_and_ref_cannot_both_be_set() -> None:
    """Two inputs, two different claims about what is being published.

    Both together is ambiguous: a release tag names one version and one commit,
    a ref names neither. Whichever branch won, the image would carry a name that
    does not describe it.
    """
    guards = _no_comments(_step_by_id(_doc(), "version")["run"])
    assert _refuses(guards, "set 'tag' or 'ref', not both")
    assert _refuses(guards, "to publish a release image, or 'ref'")


def test_a_ref_build_cannot_claim_a_release_name() -> None:
    """``:vX.Y.Z`` and ``:latest`` are release names; a ref build never takes one.

    The release path publishes both names from one commit that a release tag
    names. A ref path has neither property, so giving it a release name would
    re-open the exact image→commit hole this lane exists to close — and would
    make the idempotency guard skip the real tag build later.
    """
    guards = _no_comments(_step_by_id(_doc(), "version")["run"])
    # Split on the branch boundary itself, not on a name or a mode: the
    # release names and `mode="release"` sit before the `else`, and the ref
    # path's `image=` line sits before `mode="ref"`, so anchoring on either
    # would put half of one branch on the wrong side.
    release_branch, sep, ref_branch = guards.partition("\nelse\n")
    assert sep, "the resolve step no longer branches on tag vs ref"

    # The release path keeps both of its names.
    assert 'image="${image_repo}:v${version}"' in release_branch
    assert ":latest" in release_branch
    assert 'mode="release"' in release_branch

    # The ref path gets exactly one name, and it is derived from the commit.
    assert 'image="${image_repo}:sha-$(git rev-parse --short=12 HEAD)"' in ref_branch
    assert 'tags="$image"' in ref_branch, "the ref path must publish one name, not two"
    assert ":latest" not in ref_branch, "a rehearsal image must not move :latest"
    assert "sha-" not in release_branch, "a release image must not carry a rehearsal name"


def test_the_push_sends_every_name_the_resolve_step_chose() -> None:
    """One name on the ref path, two on the release path; both must actually go out.

    The names used to be hardcoded on the build step, which is why the build step
    had to be split in two. Hardcoding them again would silently drop the ref
    path's single name the moment a second name was added.
    """
    push = _no_comments(_step_by_id(_doc(), "push")["run"])
    assert 'while IFS= read -r ref' in push
    assert 'docker push "$ref"' in push
    assert '<<< "$TAGS"' in push, "the push must read the names the resolve step chose"
    assert ":latest" not in push and "digichat:v" not in push, (
        "the push step must not hardcode names — the resolve step owns them"
    )


def test_the_image_is_probed_before_it_is_pushed() -> None:
    """A boot failure must never reach a registry under a release name.

    Prod digichat is a Single-revision Container App: no traffic shift, no
    automatic rollback. And a release tag here is immutable — to replace a
    broken image you cut a new patch version. So an image that cannot serve
    ``/healthz``, pushed as ``v2.4.0``, is not recoverable by re-running this
    lane; it can only be walked back by a human who knows it happened.
    """
    steps = _steps(_doc())
    ids = [step.get("id") for step in steps]
    for needed in ("check", "build", "probe", "push"):
        assert needed in ids, f"the lane needs a {needed!r} step; step ids are {ids}"
    assert (
        ids.index("check") < ids.index("build") < ids.index("probe") < ids.index("push")
    ), f"the probe must sit between the build and the push; step ids are {ids}"
    assert "probe" in steps[ids.index("push")].get("if", ""), (
        "the push must be gated on the probe's outcome — an unconditional push "
        "publishes the image whether or not the probe passed"
    )
    # And the probe is not skipped when the probe's own precondition fails:
    # both steps share the build's condition, so neither runs on an
    # already-published version.
    assert _step_by_id(_doc(), "probe").get("if") == _step_by_id(_doc(), "build").get("if")


def test_the_probe_fails_closed() -> None:
    """200 alone is not the contract, and every refusal has to actually exit.

    ``/healthz`` is a fixed ``{"ok": true}``, so a catch-all route that shadows
    it also returns 200. And the version the image *serves* must be the version
    it was *built* as — that is what catches a stale layer or a tag that no
    longer matches the tree, and nothing else in this lane would notice it.
    """
    probe = _no_comments(_step_by_id(_doc(), "probe")["run"])
    assert "set -euo pipefail" in probe
    assert "/healthz" in probe and '!= "200"' in probe
    assert "jq -r '.ok'" in probe and '!= "true"' in probe, "the body must say ok=true, not just 200"
    assert "/api/health" in probe and '!= "$VERSION"' in probe

    for marker in (
        "the container exited before it served one probe",
        "never returned 200",
        "did not report ok=true",
        "but this image was built as",
    ):
        assert _refuses(probe, marker), (
            f"the probe reports {marker!r} but no exit 1 follows it — a diagnostic "
            "without an exit leaves the step successful and the push runs"
        )


def test_provenance_is_asserted_on_the_rehearsal_path_too() -> None:
    """A rehearsal image gets its binding proof here and nowhere else.

    ``check_digichat_image_binding.py`` runs only on the release path, because it
    validates a version against a release tag. The probe is the only place a ref
    build is held to the same commit it was built from — which is what makes a
    rehearsal image safe to promote by hand afterwards.
    """
    probe_step = _step_by_id(_doc(), "probe")
    probe = _no_comments(probe_step["run"])
    assert "org.opencontainers.image.revision" in probe
    assert '[ "$revision" != "$COMMIT" ]' in probe
    # Not conditioned on the mode: a rehearsal build is held to the binding too.
    assert "mode" not in probe_step.get("if", "")
