"""Pin the dashboard export and temporary legacy-path redirect."""

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
    assert "cp -r frontend/dashboard/out/. dist/dashboard/" in text
    assert "[ -f dist/dashboard/index.html ]" in text
    assert "mkdir -p dist/olympus" not in text
    assert "cp -r frontend/dashboard/out/. dist/olympus/" not in text
    assert "dist/olympus/index.html" not in text


def test_build_asserts_alpaca_oauth_callback_export() -> None:
    """Pages --apply pins this path; a settings 200 with a callback 404 strands OAuth."""
    text = BUILD.read_text(encoding="utf-8")
    assert "[ -f dist/dashboard/settings/brokers/callback/index.html ]" in text
    assert "alpaca-oauth-callback" in text


def test_pages_build_check_asserts_dist_dashboard() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert "test -d dist/dashboard" in text
    assert "test -d dist/olympus" not in text


def test_site_smoke_probes_dashboard_url() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    assert 'probe "https://digiquant.io/dashboard/" "text/html"' in text
    assert 'probe "https://digiquant.io/olympus/" "text/html"' not in text


def test_pages_redirects_olympus_to_dashboard_permanently() -> None:
    text = REDIRECTS.read_text(encoding="utf-8")
    assert "/olympus/*" in text
    assert "/dashboard/:splat" in text
    assert "308" in text


def test_pages_headers_do_not_scope_csp_to_olympus() -> None:
    text = HEADERS.read_text(encoding="utf-8")
    assert "/dashboard*" in text
    assert "/olympus*" not in text


def test_pages_auth_flag_is_dashboard_only() -> None:
    text = BUILD.read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_DASHBOARD_AUTH" in text
    assert "NEXT_PUBLIC_OLYMPUS_AUTH" not in text


def test_settings_kicker_is_dashboard_not_olympus() -> None:
    page = (REPO_ROOT / "frontend" / "dashboard" / "app" / "settings" / "page.tsx").read_text(
        encoding="utf-8"
    )
    assert "dashboard" in page
    assert "olympus" not in page.lower()


def test_public_app_urls_ok_pins_dashboard_not_olympus() -> None:
    """Live EF still returns /olympus until Pages+EF cutover; the hop must not accept it."""
    text = (
        REPO_ROOT / "digiquant" / "src" / "digiquant" / "olympus" / "kairos" / "staging_e2e.py"
    ).read_text(encoding="utf-8")
    assert 'f"{DEFAULT_PUBLIC_APP_ORIGIN}/dashboard/settings/brokers/callback"' in text
    assert 'f"{DEFAULT_PUBLIC_APP_ORIGIN}/dashboard/settings/"' in text
    assert "/olympus/settings" not in text
