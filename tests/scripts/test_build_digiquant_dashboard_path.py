"""Pin the dashboard export to dist/dashboard/ — no olympus twin, 308, or probe."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / "scripts" / "build-digiquant.sh"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy-digiquant-cloudflare.yml"
SMOKE = REPO_ROOT / ".github" / "workflows" / "smoke-site.yml"
REDIRECTS = REPO_ROOT / "frontend" / "digiquant-web" / "public" / "_redirects"
HEADERS = REPO_ROOT / "frontend" / "digiquant-web" / "public" / "_headers"


def test_build_copies_dashboard_export_only_to_dist_dashboard() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "mkdir -p dist/dashboard" in text
    assert "cp -r frontend/olympus/out/. dist/dashboard/" in text
    assert "[ -f dist/dashboard/index.html ]" in text
    assert "mkdir -p dist/olympus" not in text
    assert "cp -r frontend/olympus/out/. dist/olympus/" not in text
    assert "dist/olympus/index.html" not in text


def test_pages_build_check_asserts_dist_dashboard() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "test -d dist/dashboard" in text
    assert "test -d dist/olympus" not in text


def test_site_smoke_probes_dashboard_url() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    assert 'probe "https://digiquant.io/dashboard/" "text/html"' in text
    assert 'probe "https://digiquant.io/olympus/" "text/html"' not in text


def test_pages_redirects_have_no_olympus_rules() -> None:
    text = REDIRECTS.read_text(encoding="utf-8")
    assert "/olympus" not in text
    assert "308" not in text


def test_pages_headers_do_not_scope_csp_to_olympus() -> None:
    text = HEADERS.read_text(encoding="utf-8")
    assert "/dashboard*" in text
    assert "/olympus*" not in text


def test_pages_auth_flag_is_dashboard_only() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DASHBOARD_AUTH" in text
    assert "NEXT_PUBLIC_OLYMPUS_AUTH" not in text


def test_settings_kicker_is_dashboard_not_olympus() -> None:
    page = (REPO_ROOT / "frontend" / "olympus" / "app" / "settings" / "page.tsx").read_text(
        encoding="utf-8"
    )
    assert "dashboard" in page
    assert "olympus" not in page.lower()
