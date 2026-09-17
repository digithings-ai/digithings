"""Pin wave 3: the dashboard workspace lives at cloudflare/dashboard.

ADR-0026 wave 3. Public URL is /dashboard/ only; Python digiquant.dashboard
and CSS .oly-* are unchanged. /olympus/ has no source twin; Pages redirects it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG = REPO_ROOT / "cloudflare" / "dashboard" / "package.json"
OLD = REPO_ROOT / "cloudflare" / "olympus"
BUILD = REPO_ROOT / "scripts" / "build-digiquant.sh"
CI_PATHS = REPO_ROOT / "scripts" / "ci_paths.yaml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test-dashboard.yml"
CANON = REPO_ROOT / "scripts" / "check_frontend_canon.py"


def test_workspace_folder_is_frontend_dashboard() -> None:
    assert PKG.is_file(), "cloudflare/dashboard/package.json must exist"
    assert not OLD.exists(), "cloudflare/olympus must be gone (git mv, not a copy)"
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    assert pkg["name"] == "dashboard"


def test_build_copies_from_frontend_dashboard() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "cp -r cloudflare/dashboard/out/. dist/dashboard/" in text
    assert "cloudflare/olympus" not in text


def test_ci_lane_is_dashboard() -> None:
    text = CI_PATHS.read_text(encoding="utf-8")
    assert "cloudflare/dashboard/**" in text
    assert "test-dashboard.yml" in text
    assert "cloudflare/olympus/**" not in text


def test_reusable_workflow_uses_dashboard_workspace() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "npm run lint --workspace dashboard" in text
    assert "npm run build --workspace dashboard" in text
    assert "npm run test --workspace dashboard" in text
    assert "--workspace olympus" not in text


def test_canon_census_app_is_dashboard_folder() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert '"dashboard"' in text or "'dashboard'" in text
    assert "cloudflare/dashboard/lib/chart-colors.ts" in text
    assert "cloudflare/olympus/" not in text


def test_dashboard_does_not_ship_olympus_public_env_keys() -> None:
    env = (REPO_ROOT / "cloudflare" / "dashboard" / ".env.local.example").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_OLYMPUS" not in env
    assert "NEXT_PUBLIC_DASHBOARD_AUTH" in env
    assert "NEXT_PUBLIC_DIGICHAT_POPUP" in env
    build = BUILD.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_OLYMPUS" not in build
    assert "NEXT_PUBLIC_DIGICHAT_POPUP=1" in build
    assert "NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai" in build
    assert "NEXT_PUBLIC_DIGICHAT_EMBED_HOST=digiquant.io" in build
    shell = (
        REPO_ROOT / "cloudflare" / "dashboard" / "components" / "app-shell-context.tsx"
    ).read_text(encoding="utf-8")
    assert "dashboard-sidebar-collapsed" in shell
    assert "localStorage.setItem(STORAGE_KEY" in shell


def test_dockerfiles_copy_dashboard_package_json() -> None:
    for rel in ("cloudflare/digichat/Dockerfile", "Dockerfile.digichat-cloudflare"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "cloudflare/dashboard/package.json" in text
        assert "cloudflare/olympus/package.json" not in text


def test_gitignore_ignores_dashboard_static_portfolio() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "cloudflare/dashboard/public/dashboard-data.json" in text
    assert "cloudflare/olympus/public/dashboard-data.json" not in text


def test_dashboard_has_no_nested_lockfile() -> None:
    assert not (REPO_ROOT / "cloudflare" / "dashboard" / "package-lock.json").exists()


def test_dashboard_icons_and_theme_keys_are_not_olympus() -> None:
    layout = (REPO_ROOT / "cloudflare" / "dashboard" / "app" / "layout.tsx").read_text(
        encoding="utf-8"
    )
    manifest = (REPO_ROOT / "cloudflare" / "dashboard" / "app" / "manifest.ts").read_text(
        encoding="utf-8"
    )
    theme = (REPO_ROOT / "cloudflare" / "dashboard" / "components" / "theme-provider.tsx").read_text(
        encoding="utf-8"
    )
    icons = REPO_ROOT / "cloudflare" / "dashboard" / "public" / "icons"
    assert "dashboard-app-dark.svg" in layout
    assert "olympus-app-" not in layout
    assert "olympus-app-" not in manifest
    assert "dashboard-theme" in layout
    assert "dashboard-theme" in theme
    assert "localStorage.setItem(STORAGE_KEY" in theme
    assert (icons / "dashboard-app-dark.svg").is_file()
    assert not (icons / "olympus-app-dark.svg").exists()
