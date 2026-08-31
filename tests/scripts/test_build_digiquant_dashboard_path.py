"""Pin the dashboard export to dist/dashboard/ — no twin at dist/olympus/.

Wave 2 served both so cursor/* PRs could not edit deploy-digiquant-cloudflare.yml.
The path is /dashboard/; Cloudflare _redirects 308 /olympus/* onto it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD = REPO_ROOT / "scripts" / "build-digiquant.sh"
DEPLOY = REPO_ROOT / ".github" / "workflows" / "deploy-digiquant-cloudflare.yml"
SMOKE = REPO_ROOT / ".github" / "workflows" / "smoke-site.yml"


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
    # 308 from /olympus/ must still follow to HTML (curl -sL in the workflow).
    assert 'probe "https://digiquant.io/olympus/" "text/html"' in text
