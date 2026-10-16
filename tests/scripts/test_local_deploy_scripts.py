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
