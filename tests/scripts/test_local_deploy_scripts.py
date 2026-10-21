"""Local build/deploy/publish scripts replace the disabled GitHub lanes.

Covers scripts/local-deploy/* (DIG-3606): every script is present and
executable, dry-by-default with a named-approval live gate, the worker set
is derived the same way as test_worker_build_matrix.py, and no script
embeds a secret. No network, Docker or Cloudflare credential is needed.
"""

from __future__ import annotations

import json
import re
import shutil
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


_PROBE_PROGRAMS = re.compile(r"node -e '(.*?)' <<< \"\$api_body\"", re.S)


def _probe_programs(script: str) -> list[str]:
    """The programs the probe runs on the health body, in file order."""
    programs = _PROBE_PROGRAMS.findall(script)
    assert len(programs) >= 2, (
        "the probe must read the health body through node: one program for the "
        "version it serves, one for the checks it reports"
    )
    return programs


def _probe_output(program: str, body: str) -> str:
    result = subprocess.run(
        ["node", "-e", program],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout


def test_the_local_publish_probe_holds_the_ci_probe_contract() -> None:
    """The rehearsal has to fail where the CI lane fails.

    A rehearsal that passes where the CI probe fails is worse than no
    rehearsal: it reports the lane green while the lane is red. The CI probe
    boots the image bare and reads the /api/health status instead of demanding
    a 200 - a standalone container has no ecosystem services to reach, so 503
    is the expected answer - so the local probe has to do the same.

    The text assertions run against the executable text, with the comments
    stripped: a substring check that a comment can satisfy proves nothing. The
    verdict is then pinned behaviourally: the probe's own node programs are
    driven with the bodies the health route can produce, so widening the
    tolerated set, dropping a requirement or moving the sentinel into a
    payload value all fail here.
    """
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe's own programs")
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
    # The status is READ, and only the two honest answers are accepted: a 500
    # that still serialises the version is a fault, not a degraded environment.
    assert "api_status" in body, "the probe must read the status code, not demand one"
    assert "--write-out" in body, "the probe must read the status code it accepts"
    assert "200|503)" in body, (
        "the probe must accept only 200 and 503: any other status is a fault"
    )
    assert "curl_rc" in body, (
        "a transfer that never completed is not an answer: the probe has to "
        "tell a timeout apart from a status the image served"
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
    assert _refuses(
        body, "serves version"
    ), "a wrong version without an exit behind it publishes the wrong image"

    version_program, checks_program = _probe_programs(script)[:2]

    # A bare container: the four ecosystem services cannot be reached, so the
    # route answers 503 with four "unreachable" and the probe has to accept it.
    bare = {
        "version": "2.6.4",
        "checks": {
            "service": "ok",
            "database": "skipped",
            "digraph": "unreachable",
            "digisearch": "unreachable",
            "digiquant": "unreachable",
            "digitrace": "unreachable",
        },
    }
    assert _probe_output(version_program, json.dumps(bare)) == "2.6.4"
    assert _probe_output(checks_program, json.dumps(bare)).startswith("CLEAN"), (
        "the bare-container degradation is what the probe has to tolerate"
    )

    # An upstream that ANSWERED is a fault, not a degradation.
    answered = {
        "version": "2.6.4",
        "checks": {"service": "ok", "database": "skipped", "digraph": "http_500"},
    }
    assert _probe_output(checks_program, json.dumps(answered)).startswith("BAD:"), (
        "a service that answered http_<status> must not be tolerated"
    )

    # A broken service, a broken database, a missing service and a missing
    # checks block are all faults.
    for checks in (
        {"service": "error", "database": "skipped"},
        {"service": "ok", "database": "error"},
        {"database": "skipped"},
    ):
        payload = json.dumps({"version": "2.6.4", "checks": checks})
        assert _probe_output(checks_program, payload).startswith("BAD:"), (
            f"the probe must refuse {checks}"
        )
    assert _probe_output(checks_program, json.dumps({"version": "2.6.4"})).startswith(
        "BAD:"
    ), "a body with no checks at all must be refused"

    # A check whose key collides with the old success sentinel must not pass.
    collides = {
        "version": "2.6.4",
        "checks": {"service": "ok", "database": "skipped", "ok": "error"},
    }
    assert _probe_output(checks_program, json.dumps(collides)).startswith("BAD:"), (
        "the success sentinel must not be a value the payload can produce"
    )

    # The version program reports the version in the body, so the shell can
    # refuse an image that serves the wrong one.
    assert _probe_output(version_program, json.dumps({"version": "2.5.0"})) == "2.5.0"
    assert _probe_output(version_program, "<html>gateway error</html>") == "NOTJSON", (
        "a body that is not JSON has to be told apart from a JSON body without "
        "a version"
    )
    assert _probe_output(version_program, json.dumps({"status": "ok"})) == "NOVERSION"
