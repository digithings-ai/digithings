"""Pin a transitional /dashboard twin on the main Pages build.

Live Pages still serve /olympus (200) and 404 /dashboard. Staging E2E pins
EF callback URLs to /dashboard, so the Pages half of the cutover is a second
static export of frontend/olympus with OLYMPUS_BASE_PATH=/dashboard.
Develop has already retired the olympus twin — this pin is main-only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / "scripts" / "build-digiquant.sh"
NEXT_CONFIG = REPO_ROOT / "frontend" / "olympus" / "next.config.mjs"
HEADERS = REPO_ROOT / "frontend" / "digiquant-web" / "public" / "_headers"


def test_next_config_allows_dashboard_base_path() -> None:
    text = NEXT_CONFIG.read_text(encoding="utf-8")
    assert "OLYMPUS_BASE_PATH" in text
    assert "'/olympus'" in text
    assert "'/dashboard'" in text


def test_build_exports_olympus_and_dashboard_twins() -> None:
    text = BUILD.read_text(encoding="utf-8")
    olympus_cmd = "OLYMPUS_BASE_PATH=/olympus npm --workspace frontend/olympus run build"
    dashboard_cmd = "OLYMPUS_BASE_PATH=/dashboard npm --workspace frontend/olympus run build"
    assert olympus_cmd in text
    assert dashboard_cmd in text
    # Caller env / leftover .next must not leak the twin prefix into /olympus.
    # Compare the npm invocations, not the header comment that names both paths.
    assert text.index(olympus_cmd) < text.index(dashboard_cmd)
    assert "rm -rf frontend/olympus/out frontend/olympus/.next" in text
    assert "mkdir -p dist/dashboard" in text
    assert "cp -r frontend/olympus/out/. dist/dashboard/" in text
    assert "[ -f dist/dashboard/index.html ]" in text
    assert "[ -f dist/dashboard/login/index.html ]" in text
    assert "[ -f dist/dashboard/auth/callback/index.html ]" in text
    assert "[ -f dist/dashboard/settings/brokers/callback/index.html ]" in text
    assert "alpaca-oauth-callback" in text
    assert "[ -f dist/dashboard/settings/index.html ]" in text
    assert "[ -f dist/olympus/index.html ]" in text


def test_headers_csp_covers_both_public_paths() -> None:
    text = HEADERS.read_text(encoding="utf-8")
    assert "/olympus*" in text
    assert "/dashboard*" in text
    assert text.count("Content-Security-Policy:") == 2
