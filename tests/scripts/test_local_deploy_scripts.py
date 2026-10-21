"""Local build/deploy/publish scripts replace the disabled GitHub lanes.

Covers scripts/local-deploy/* (DIG-3606): every script is present and
executable, dry-by-default with a named-approval live gate, the worker set
is derived the same way as test_worker_build_matrix.py, and no script
embeds a secret. No network, Docker or Cloudflare credential is needed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DIR = REPO_ROOT / "scripts" / "local-deploy"

WORKER_APPS = [
    "digithings-cron",
    "dashboard-api",
    "digiquant-runner",
    "digitrace-langfuse",
    "digichat-cloudflare",
    "digithings-stack-cloudflare",
]


def read(name: str) -> str:
    return (DIR / name).read_text()


def test_scripts_present_and_executable() -> None:
    for name in (
        "build_workers.sh",
        "build_sites.sh",
        "deploy_worker.sh",
        "publish_image.sh",
        "README.md",
    ):
        assert (DIR / name).is_file(), f"missing {name}"
    for name in (
        "build_workers.sh",
        "build_sites.sh",
        "deploy_worker.sh",
        "publish_image.sh",
    ):
        assert (DIR / name).stat().st_mode & 0o111, f"{name} not executable"


def test_scripts_parse() -> None:
    for name in (
        "build_workers.sh",
        "build_sites.sh",
        "deploy_worker.sh",
        "publish_image.sh",
    ):
        proc = subprocess.run(["bash", "-n", str(DIR / name)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_worker_set_matches_matrix_derivation() -> None:
    body = read("build_workers.sh")
    assert "wrangler.toml" in body
    assert "devDependencies" not in body or "package.json" in body
    # Same predicate as test_worker_build_matrix._buildable_workers.
    derived = {
        p.parent.name
        for p in (REPO_ROOT / "apps").glob("*/package.json")
        if (p.parent / "wrangler.toml").is_file() and '"wrangler"' in p.read_text()
    }
    assert set(WORKER_APPS) <= derived, (
        f"known workers missing from derivation: {set(WORKER_APPS) - derived}"
    )
    assert "digithings-web" not in derived, "Pages app must not derive as a Worker"


def test_build_workers_is_credential_free() -> None:
    body = read("build_workers.sh")
    assert "--dry-run" in body
    assert "--containers-rollout=none" in body
    assert "CLOUDFLARE_API_TOKEN" not in body
    assert "--live" not in body


def test_deploy_worker_dry_by_default_and_approved_live() -> None:
    body = read("deploy_worker.sh")
    assert "--dry-run" in body
    # The mandatory guard itself, not just the variable name: removing it
    # must fail this test (mutant-proved).
    assert ': "${LOCAL_DEPLOY_APPROVED_BY:?' in body
    assert "CLOUDFLARE_API_TOKEN" in body
    assert "CLOUDFLARE_ACCOUNT_ID" in body
    # Exactly one live `wrangler deploy`; every other mention is dry-run.
    live_deploys = re.findall(r"wrangler deploy(?! --dry-run)", body)
    assert len(live_deploys) == 1, f"expected one live deploy, found {live_deploys}"


def test_deploy_worker_runs_gates_before_deploy() -> None:
    body = read("deploy_worker.sh")
    test_cmd = 'npm run test --workspace "$PKG"'
    dry_cmd = '(cd "apps/$APP" && npm exec -- wrangler deploy --dry-run'
    assert test_cmd in body
    assert dry_cmd in body
    assert body.index(test_cmd) < body.index(dry_cmd)
    assert 'npm run typecheck --workspace "$PKG"' in body


def test_publish_image_never_pushes_by_default() -> None:
    body = read("publish_image.sh")
    assert "PUSH=0" in body
    # The mandatory guard itself, not just the variable name.
    assert ': "${LOCAL_DEPLOY_APPROVED_BY:?' in body
    assert "manifest unknown" in body
    # Release-name discipline from both lanes.
    assert "digichat-v" in body
    assert "digillm-v" in body
    assert "sha-" in body
    # A rehearsal name must never be pushed.
    assert "must never be pushed" in body


def test_no_embedded_secrets() -> None:
    for name in (
        "build_workers.sh",
        "build_sites.sh",
        "deploy_worker.sh",
        "publish_image.sh",
    ):
        body = read(name)
        assert "CLOUDFLARE_API_TOKEN=" not in body, f"{name} embeds a token"
        assert "ghp_" not in body, f"{name} embeds a token"
        assert "sk-" not in body or "sk-smoke" in body, f"{name} embeds a key"


def test_readme_maps_every_disabled_lane() -> None:
    body = read("README.md")
    for lane in (
        "build-cloudflare-workers",
        "deploy-digiquant-cloudflare",
        "deploy-digithings-cloudflare",
        "deploy-digithings-cron",
        "deploy-digiquant-runner",
        "publish-digichat-image",
        "publish-digillm-image",
    ):
        assert lane in body, f"README does not map {lane}"


def test_publish_image_packages_the_digichat_inputs_before_it_builds() -> None:
    """The local lane builds the same image the CI lane publishes.

    Its build context is the repo root and the Dockerfile COPYs
    image-packages/digichat/, so the local lane needs the same packaging step
    the CI lane now has — otherwise the local rehearsal fails exactly where
    the CI one did.
    """
    body = read("publish_image.sh")
    pack = body.index("package_r5_image_inputs.py --npm-only")
    build = body.index("docker build")
    assert pack < build, "the inputs must be packaged before the build"
    assert "--npm-only" in body, "only the npm inputs are packaged for this image"


def _no_comments(script: str) -> str:
    """Strip shell comments, so prose in a comment block cannot satisfy an assertion.

    The trap the workflow test closes, for this script: moving a guard into the
    comment block above it leaves the assertions green and the lane unguarded.
    A ``#`` inside a quoted literal is left alone: stripping it would change
    the text under test without changing what the script does.
    """
    stripped: list[str] = []
    for line in script.splitlines():
        quote = ""
        cut = len(line)
        for index, char in enumerate(line):
            if quote:
                if char == quote:
                    quote = ""
                continue
            if char in "'\"":
                quote = char
                continue
            if char == "#" and (index == 0 or line[index - 1].isspace()):
                cut = index
                break
        stripped.append(line[:cut])
    return "\n".join(stripped)


def _refuses(guards: str, marker: str) -> bool:
    """True when the diagnostic ``marker`` is followed by an ``exit 1``.

    A refusal that prints an error and keeps going is not a refusal. This
    script writes its guards as one-liners, so the exit sits on the message's
    own line or within the next few lines.
    """
    lines = guards.splitlines()
    for index, line in enumerate(lines):
        if marker in line:
            if "exit 1" in "\n".join(lines[index : index + 3]):
                return True
    return False


def test_the_local_publish_probe_holds_the_ci_probe_contract() -> None:
    """The rehearsal has to judge the image the way the CI lane judges it.

    A rehearsal that passes where the CI probe fails is worse than no
    rehearsal: it reports the lane green while the lane is red. The two
    lanes used to keep their own copy of the rules and drifted - the local
    lane never read the status code the CI lane read - so the rules now
    live in scripts/digichat_probe_verdict.mjs and both lanes call it. The
    rules themselves are pinned by behaviour in
    tests/scripts/test_digichat_probe_verdict.py; what is pinned here is
    that this lane really calls the shared helper, reads the status and
    exits on a refusal.

    The text assertions run against the executable text, with the comments
    stripped: a substring check that a comment can satisfy proves nothing.
    """
    script = read("publish_image.sh")
    body = _no_comments(script)
    assert 'docker run --detach --rm --publish 127.0.0.1::3000 "$NAME"' in body, (
        "the digichat probe must boot the image bare, the way the CI probe does"
    )
    assert "-e DIGICHAT_ENABLED_SERVICES=" not in body, (
        "an environment flag in the probe proves a configuration the release "
        "never runs, and hides the ecosystem degradation the CI probe reports"
    )
    assert '--fail "$base/api/health"' not in body, (
        "a bare container answers /api/health with 503; --fail turns the "
        "expected degradation into a red rehearsal"
    )
    # The status is READ, not demanded.
    assert "api_status" in body, "the probe must read the status code, not demand one"
    assert "--write-out" in body, "the probe must read the status code it accepts"
    assert "curl_rc" in body, (
        "a transfer that never completed is not an answer: the probe has to "
        "tell a timeout apart from a status the image served"
    )
    # The rules are the shared helper's, not a second copy of them.
    assert "scripts/digichat_probe_verdict.mjs" in body, (
        "the rehearsal must judge the image with the same helper the CI lane "
        "uses, so the two cannot drift apart again"
    )
    assert '--status "$api_status"' in body and '--version "$VERSION"' in body, (
        "the helper has to be given the status it read and the version the "
        "image was built as"
    )
    # And the refusal has to actually exit.
    assert _refuses(body, "REFUSE"), (
        "a diagnostic without an exit behind it reports success and the publish goes on"
    )


def test_the_local_publish_binds_the_image_to_the_tree_it_builds() -> None:
    """A release image may not carry the label of a commit it was not built from.

    The local lane builds the working tree, so a tag whose commit is not the
    checked-out HEAD would be labelled with a commit the image does not
    contain. The GitHub lane checks the tag out and compares HEAD with it;
    the rehearsal has to hold the same line.
    """
    body = _no_comments(read("publish_image.sh"))
    assert 'head_commit="$(git rev-parse HEAD' in body, (
        "the rehearsal must resolve the commit it actually builds from"
    )
    assert 'if [ "$head_commit" != "$COMMIT" ]; then' in body, (
        "the rehearsal must refuse to label an image with a commit it was not "
        "built from"
    )
    assert _refuses(body, "check the tag out"), (
        "a refusal to publish an unbound image has to stop the publish"
    )


def _marked_block(body: str, name: str) -> str:
    match = re.search(rf"# {name}:begin\n(.*?)# {name}:end", body, re.S)
    assert match, f"the {name} block is not marked in publish_image.sh"
    return match.group(1)


def test_the_probe_refuses_on_the_verdict_text_and_not_on_the_exit_status(tmp_path: Path) -> None:
    """A helper that refuses but exits 0 still stops the lane.

    The decision is the helper's OUTPUT. If it were the exit status, a wrapper
    that swallowed the status would turn a refusal into a pass and the lane
    would publish an image it just refused.
    """
    body = read("publish_image.sh")
    block = _marked_block(body, "probe-verdict")
    stub = tmp_path / "stub_helper.sh"
    stub.write_text("printf 'REFUSE stubbed refusal\\n'\n")
    block = block.replace("node scripts/digichat_probe_verdict.mjs", f"cat {stub}")
    script = tmp_path / "probe.sh"
    script.write_text(
        "set -u\napi_body='{}'\napi_status='503'\nVERSION='2.6.4'\n" + block
    )
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "stubbed refusal" in result.stderr


def test_the_tree_guard_refuses_a_tree_that_is_not_the_tag(tmp_path: Path) -> None:
    """The guard is a plain comparison, so no operator can turn it into a no-op."""
    body = read("publish_image.sh")
    block = _marked_block(body, "tree-guard")
    script = tmp_path / "guard.sh"
    script.write_text("set -u\nhead_commit=aaaa\nCOMMIT=bbbb\nTAG=v9.9.9\n" + block)
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "check the tag out" in result.stderr
    script.write_text("set -u\nhead_commit=aaaa\nCOMMIT=aaaa\nTAG=v9.9.9\n" + block)
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
