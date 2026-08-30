"""Pin wave 3: the dashboard workspace lives at frontend/dashboard.

ADR-0026 wave 3. Public URL is /dashboard/ only; Python digiquant.olympus
and CSS .oly-* are unchanged. /olympus/ is retired (no 308).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG = REPO_ROOT / "frontend" / "dashboard" / "package.json"
OLD = REPO_ROOT / "frontend" / "olympus"
BUILD = REPO_ROOT / "scripts" / "build-digiquant.sh"
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-dashboard.yml"
CANON = REPO_ROOT / "scripts" / "check_frontend_canon.py"


def test_workspace_folder_is_frontend_dashboard() -> None:
    assert PKG.is_file(), "frontend/dashboard/package.json must exist"
    assert not OLD.exists(), "frontend/olympus must be gone (git mv, not a copy)"
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    assert pkg["name"] == "dashboard"


def test_build_copies_from_frontend_dashboard() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "cp -r frontend/dashboard/out/. dist/dashboard/" in text
    assert "frontend/olympus" not in text


def test_ci_lane_is_dashboard() -> None:
    text = CI_PATHS.read_text(encoding="utf-8")
    assert "frontend/dashboard/**" in text
    assert "test-dashboard.yml" in text
    assert "frontend/olympus/**" not in text


def test_reusable_workflow_uses_dashboard_workspace() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "npm run lint --workspace dashboard" in text
    assert "npm run build --workspace dashboard" in text
    assert "npm run test --workspace dashboard" in text
    assert "--workspace olympus" not in text


def test_canon_census_app_is_dashboard_folder() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert '"dashboard"' in text or "'dashboard'" in text
    assert "frontend/dashboard/lib/chart-colors.ts" in text
    assert "frontend/olympus/" not in text


def test_dashboard_does_not_ship_olympus_public_env_keys() -> None:
    env = (REPO_ROOT / "frontend" / "dashboard" / ".env.local.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_OLYMPUS" not in env
    assert "NEXT_PUBLIC_DASHBOARD_AUTH" in env
    build = BUILD.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_OLYMPUS" not in build
    shell = (
        REPO_ROOT / "frontend" / "dashboard" / "components" / "app-shell-context.tsx"
    ).read_text(encoding="utf-8")
    assert "dashboard-sidebar-collapsed" in shell
    assert "localStorage.setItem(STORAGE_KEY" in shell
