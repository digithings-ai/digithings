"""Model-routing coverage: every phase slug must resolve via digiquant_models.yaml.

A slug without dashboard capability mapping (and without a non-flagship ``phase_models``
override) falls back through ``get_model_for_mode()`` to the hard-coded ``gpt-4o-mini``
last resort, which digillm routes to the default OpenAI client — unauthenticated in the
research CI workflows, where only ``OPENROUTER_API_KEY`` is provided. That is exactly how the
``alt-ai-portfolios`` segment 401'd every scheduled delta run (#678). Segment slugs are
derived from the phase specs themselves so a new segment cannot ship without a routing entry.
"""

from __future__ import annotations

from pathlib import Path

import digigraph.model_config as model_config
import pytest
from digiquant.research.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.research.phases.phase2_institutional import _SPECS as INST_SPECS
from digiquant.research.phases.phase3_macro import _SPEC as MACRO_SPEC
from digiquant.research.phases.phase4_assetclass import _SPECS as ASSET_SPECS
from digiquant.research.sectors_config import load_sectors

_REPO_CONFIG = str(Path(__file__).parents[3] / "config")

# Static phase_slug literals passed to run_research_agent outside the
# SegmentNodeSpec fan-outs (regenerate with: git grep -h 'phase_slug="'
# -- digiquant/src/digiquant/dashboard).
_STATIC_PHASE_SLUGS = (
    "equity",
    "master-digest",
    "monthly-digest",
    "pm-rebalance",
    "risk-aggressive",
    "risk-conservative",
    "phase9-evolution",
    "decision-reflector",
    "beliefs-distillation",
)

# Dynamic per-ticker slugs, prefix-matched in digiquant_models.yaml ("<prefix>-").
_DYNAMIC_SLUG_EXAMPLES = (
    "technical-analyst-AAPL",
    "sentiment-analyst-AAPL",
    "news-analyst-AAPL",
    "fundamental-analyst-AAPL",
    "bull-researcher-AAPL",
    "bear-researcher-AAPL",
    "research-manager-AAPL",
)

# portfolio H1–H7 phase_slug literals (see digiquant/portfolio/phases/*).
_PORTFOLIO_STATIC_SLUGS = (
    "portfolio/thesis/market-review",
    "portfolio/thesis/market-exploration",
    "portfolio/thesis/vehicle-map",
    "portfolio/pm-direction",
)

_PORTFOLIO_DYNAMIC_SLUG_EXAMPLES = (
    "portfolio/asset-analyst-AAPL",
    "h6_pm_challenge-AAPL",
    "h6_analyst_response-AAPL",
)


def _all_slugs() -> list[str]:
    specs = (*ALT_SPECS, *INST_SPECS, MACRO_SPEC, *ASSET_SPECS)
    slugs = [spec.segment_slug for spec in specs]
    slugs += [sector.slug for sector in load_sectors()]
    slugs += [
        *_STATIC_PHASE_SLUGS,
        *_DYNAMIC_SLUG_EXAMPLES,
        *_PORTFOLIO_STATIC_SLUGS,
        *_PORTFOLIO_DYNAMIC_SLUG_EXAMPLES,
    ]
    return slugs


@pytest.mark.unit
def test_every_phase_slug_has_model_routing(monkeypatch):
    monkeypatch.setenv("DIGI_CONFIG_PATH", _REPO_CONFIG)
    # The model-modes cache is keyed by mtime only (not path); reset it so an
    # earlier test that loaded a different model_modes file can't leak in here.
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    load_sectors.cache_clear()
    missing = sorted(
        slug for slug in _all_slugs() if model_config.get_model_for_phase(slug) is None
    )
    assert not missing, (
        f"phase slugs missing digiquant_models.yaml capability routing: {missing} — "
        "without a mapping they fall back to the unauthenticated gpt-4o-mini "
        "default and 401 in CI (#678)"
    )
