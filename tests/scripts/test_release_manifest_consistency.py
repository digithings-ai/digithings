"""Guards release-please's bookkeeping against the drift that produced two untagged releases.

WHAT WENT WRONG. `release-please-digichat.yml` watched `module/digichat`, but that branch
stopped moving the day `digichat-v0.6.0` was cut — it still points at exactly that release
commit, 44 commits behind develop — while digichat work kept merging straight to develop.
So the tool never saw the changes, and two releases were hand-written to imitate its
output instead:

* 0.7.0 — `d9b4f6fe`, titled `chore(module/digichat): release digichat 0.7.0` on a branch
  it never touched. It reached `main` and shipped to production with no tag.
* 0.8.0 — `df3999dc`, same shape.

Their CHANGELOG entries linked `compare/digichat-v0.7.0...digichat-v0.8.0` against two
tags that did not exist, and because `.release-please-manifest.json` read 0.8.0, the
tool's next run would have proposed 0.9.0 comparing against a still-missing 0.8.0 —
the broken link propagating forward indefinitely.

WHAT THESE TESTS PIN. The manifest is release-please's source of truth for "what is
already released", and `package.json` is what `publish-digichat-image.yml` actually reads
(`jq -r .version`) to decide the image tag. When those two disagree, the tool and the
deploy disagree about which version exists. That is checkable from files alone, with no
network and no tags, so it is checked here.

Tag existence is deliberately NOT asserted: `tests/scripts/` runs in a lane that does not
fetch tags, so the assertion would fail for an environmental reason rather than a real
one — the exact unrelated-red that gets a check disabled. The workflow header carries the
tag history in prose instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".release-please-manifest.json"
CONFIG = REPO_ROOT / "release-please-config.json"
DIGICHAT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-please-digichat.yml"


def _manifest() -> dict[str, str]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _config() -> dict[str, object]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


@pytest.mark.unit
def test_every_managed_package_declares_the_version_the_manifest_claims() -> None:
    """The manifest and each package.json must agree.

    release-please reads the manifest to decide the next version; the image publish
    reads package.json to decide the tag it pushes. A mismatch means the release tool
    and the deploy disagree about which version exists — which is how 0.8.0 ended up
    recorded as released while the lockfile still said 0.7.0.
    """
    packages = _config()["packages"]
    assert isinstance(packages, dict) and packages, "release-please manages nothing?"

    manifest = _manifest()
    for pkg_path in packages:
        declared = manifest.get(pkg_path)
        assert declared, f"{pkg_path} is release-please-managed but absent from the manifest"

        pkg_json = REPO_ROOT / pkg_path / "package.json"
        assert pkg_json.is_file(), f"{pkg_path}/package.json is missing"
        actual = json.loads(pkg_json.read_text(encoding="utf-8"))["version"]

        assert actual == declared, (
            f"{pkg_path}: package.json says {actual}, manifest says {declared}. "
            "release-please would cut the next release from the manifest while the image "
            "publish tags from package.json — reconcile before releasing."
        )


@pytest.mark.unit
def test_the_lockfile_records_the_same_version_as_each_managed_package() -> None:
    """npm records workspace versions in the lockfile, and it lags a hand-cut bump.

    Caught after the fact three times on digichat — 0.3.0 → 0.5.0 (in an unrelated
    website PR), 0.5.0 → 0.7.0, then 0.7.0 → 0.8.0 — every time as a stray hunk in a PR
    about something else. `npm install` fixes it; this says so before the fact.
    """
    lock = json.loads((REPO_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    packages = lock.get("packages", {})

    for pkg_path in _config()["packages"]:
        entry = packages.get(pkg_path)
        if entry is None:
            continue  # not an npm workspace — nothing for the lockfile to record
        recorded = entry.get("version")
        declared = json.loads((REPO_ROOT / pkg_path / "package.json").read_text(encoding="utf-8"))[
            "version"
        ]
        assert recorded == declared, (
            f"{pkg_path}: package-lock.json records {recorded} but package.json says "
            f"{declared} — run `npm install` to resync the lockfile."
        )


@pytest.mark.unit
def test_release_please_targets_a_branch_the_work_actually_lands_on() -> None:
    """The whole defect in one assertion.

    A release workflow pointed at a branch nothing merges into produces no releases and
    invites someone to hand-write them, which is exactly what happened on
    module/digichat. digichat is frontend and merges to develop.
    """
    wf = DIGICHAT_WORKFLOW.read_text(encoding="utf-8")
    commands = "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))
    assert "target-branch: develop" in commands
    assert "module/digichat" not in commands, (
        "module/digichat has not moved since digichat-v0.6.0 — targeting it means no "
        "release ever fires"
    )
    # Not main: a squashed promotion commit reads as a no-op to a Conventional Commits
    # parser and would swallow the real feat/fix signal (#1343).
    assert "target-branch: main" not in commands


@pytest.mark.unit
def test_digichat_release_bumps_the_root_workspace_lockfile() -> None:
    """release-type node only updates a sibling package-lock.json (#1974).

    Under npm workspaces the lockfile lives at the repo root, so a digichat release
    PR that only touched package.json + CHANGELOG + the manifest left
    ``packages['frontend/digichat'].version`` stale until a hand ``npm install``.
    The GenericJson extra-file must keep that field in the same release commit.
    """
    packages = _config()["packages"]
    assert isinstance(packages, dict)
    digichat = packages["frontend/digichat"]
    assert isinstance(digichat, dict)
    extras = digichat.get("extra-files")
    assert isinstance(extras, list) and extras, "digichat must declare extra-files"
    lock_bumps = [
        entry
        for entry in extras
        if isinstance(entry, dict)
        and entry.get("type") == "json"
        and str(entry.get("path", "")).endswith("package-lock.json")
    ]
    assert lock_bumps, "digichat extra-files must bump the root package-lock.json"
    assert lock_bumps[0].get("jsonpath") == "$.packages['frontend/digichat'].version"


@pytest.mark.unit
def test_release_manifest_consistency_lane_sees_release_prs() -> None:
    """A release PR must not land green while this module's asserts stay skipped.

    Release PRs edit package.json + the manifest (+ now the lockfile). Those paths
    must stay in the ``ruff_and_scripts`` filter so ``test_release_manifest_consistency``
    runs on the PR that would break it, not at the next promotion (#1974).
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # Prefer the dorny path-filter list (indented under filters:), not the job
    # output passthrough on line ~40 that also names ruff_and_scripts.
    marker = "            ruff_and_scripts:\n"
    start = ci.index(marker)
    end = ci.index("            workflows:\n", start)
    block = ci[start:end]
    for path in (
        ".release-please-manifest.json",
        "frontend/digichat/package.json",
        "package-lock.json",
    ):
        assert f"'{path}'" in block or f'"{path}"' in block, (
            f"{path} missing from ruff_and_scripts — release PRs would skip this lane"
        )
