"""Pin Cloudflare Pages Settings export greps to the Observer IA.

Cloudflare git-integration sets ``CF_PAGES=1``. ``scripts/build-digiquant.sh``
then defaults ``NEXT_PUBLIC_DASHBOARD_AUTH=1``, so ``tierFromSession(null)`` is
``free`` and the static Settings shell is Notifications | Billing | About.
GitHub's deploy build check omits ``CF_PAGES``, auth stays off, and the same
page prerenders as enterprise (all Custom+ tabs). Requiring
``settings-tab-pipeline`` / ``settings-tab-keys`` on every path is why the
#3266/#3273 production deploys failed while the GH check stayed green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build-digiquant.sh"


def _settings_block() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("# Settings (T3")
    end = text.index("[ -f dist/build-info.json ]", start)
    return text[start:end]


def test_observer_ia_markers_are_required_on_every_pages_build() -> None:
    block = _settings_block()
    for marker in (
        "The desk, not the product",
        "settings-tab-notifications",
        "settings-tab-billing",
        "settings-tab-about",
    ):
        assert marker in block, f"settings export must always grep for {marker!r}"


def test_custom_tab_markers_are_gated_to_auth_off_ssg() -> None:
    block = _settings_block()
    gate = 'NEXT_PUBLIC_DASHBOARD_AUTH:-}" != "1"'
    assert gate in block, "Pipeline/Keys greps must be skipped when auth is on (CF Pages)"
    before, after = block.split(gate, 1)
    assert "settings-tab-pipeline" not in before
    assert "settings-tab-keys" not in before
    assert "settings-tab-pipeline" in after
    assert "settings-tab-keys" in after
