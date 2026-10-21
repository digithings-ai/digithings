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
    """Strip ``#`` to end of line, so prose in a comment block cannot satisfy an assertion.

    The trap the workflow test closes, for this script: moving a guard into the
    comment block above it leaves the assertions green and the lane unguarded.
    """
    return re.sub(r"#.*$", "", script, flags=re.M)


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
    """The rehearsal has to fail where the CI lane fails.

    A rehearsal that passes where the CI probe fails is worse than no
    rehearsal: it reports the lane green while the lane is red. The CI probe
    boots the image bare and reads the /api/health status instead of demanding
    a 200 - a standalone container has no ecosystem services to reach, so 503
    is the expected answer - so the local probe has to do the same.

    The assertions are on the executable text, with the comments stripped: a
    substring check that a comment can satisfy proves nothing, and the whole
    checks block can be deleted behind one.
    """
    body = _no_comments(read("publish_image.sh"))
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
    # The status is READ, and only the two honest answers are accepted: a 500
    # that still serialises the version is a fault, not a degraded environment.
    assert "api_status" in body, "the probe must read the status code, not demand one"
    assert "--write-out" in body, "the probe must read the status code it accepts"
    assert "200|503)" in body, (
        "the probe must accept only 200 and 503: any other status is a fault"
    )
    # The four ecosystem services, and only when the fetch never completed.
    for service in ("digraph", "digiquant", "digitrace", "digisearch"):
        assert service in body, (
            f"the probe must name {service} as a service a standalone container "
            "cannot reach, so its failure reads as a degradation and not a fault"
        )
    assert "unreachable" in body, (
        "the tolerated failure is the one the route records when the fetch never "
        "completed; an upstream that answered http_<status> is a real fault"
    )
    # The version is still the contract: it is what catches a stale layer.
    assert '[ "$reported" = "$VERSION" ]' in body, (
        "the version the image serves is still the contract"
    )
    # The verdict must not hang on a magic string the payload could produce.
    assert "CLEAN" in body and "BAD:" in body, (
        "the success sentinel has to be a value the health payload cannot produce"
    )
    # And the refusal has to actually exit.
    assert _refuses(
        body, "not only the unreachable ecosystem services"
    ), "a diagnostic without an exit behind it reports success and the publish goes on"
