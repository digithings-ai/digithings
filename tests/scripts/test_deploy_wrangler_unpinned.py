"""Worker deploy workflows must resolve wrangler from the lockfile, never a pin.

DIG-2438: `deploy-digithings-cron.yml` (and the in-flight
`deploy-dashboard-api.yml`) pinned `with.wranglerVersion: "4.28.0"` via
wrangler-action@v3 while the lockfile holds exactly one wrangler
(`node_modules/wrangler` -> 4.133.0) and the PR-time gate
(`build-cloudflare-workers.yml`) resolves that same 4.133.0 via
`npm exec -- wrangler deploy --dry-run`. `--containers-rollout` is absent
from 4.28.0 and present in 4.133.0, so the gate cannot run on the pinned
version at all — the fix runs one way (deploys up to the lockfile).

This test pins the agreement: no `deploy-*.yml` workflow may set
`with.wranglerVersion`. Resolving from `npm ci` + the lockfile is the
majority pattern (bare `npx wrangler deploy`); `deploy-digichat-cloudflare-container.yml`
already documents why unpinning is right (4.28.0 rejects `deploy --message`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

pytestmark = pytest.mark.unit


def _deploy_workflows() -> list[Path]:
    return sorted(WORKFLOWS_DIR.glob("deploy-*.yml"))


def _pinned_workflows() -> list[str]:
    """Deploy workflows that set with.wranglerVersion on any step."""
    pinned = []
    for workflow in _deploy_workflows():
        parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            continue
        for job in (parsed.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                with_block = step.get("with") or {}
                if isinstance(with_block, dict) and "wranglerVersion" in with_block:
                    pinned.append(workflow.name)
                    break
    return pinned


def test_deploy_workflow_set_is_not_empty() -> None:
    """Guards the sweep itself: zero files would make the pin below vacuous."""
    assert len(_deploy_workflows()) >= 3, (
        f"expected the deploy workflows, found {len(_deploy_workflows())}"
    )


def test_no_deploy_workflow_pins_wrangler_version() -> None:
    """A hand-pinned wranglerVersion drifts from the lockfile under a green tree.

    Every Worker deploy must resolve wrangler from `npm ci` + package-lock.json
    (the version the PR-time gate builds with). Re-adding a pin fails here.
    """
    assert len(_deploy_workflows()) >= 3, "deploy workflow sweep is empty"
    pinned = _pinned_workflows()
    assert not pinned, (
        f"{pinned} set with.wranglerVersion — drop the pin so the deploy "
        f"resolves wrangler from the lockfile like the PR-time gate does (DIG-2438)"
    )
