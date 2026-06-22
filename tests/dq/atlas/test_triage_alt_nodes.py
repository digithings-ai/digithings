"""Triage coverage for the two Phase-1 alt-data segments that previously had
no rule entry (#929):

- ``alt-onchain-positioning`` — carries when the deterministic Hyperdash
  injection (``data_layer.market_context.onchain_positioning``) is byte-for-byte
  unchanged vs. the prior run's persisted snapshot; regenerates otherwise.
- ``alt-ai-portfolios`` — low-tier: mandatory regen on baseline (handled by the
  baseline run never triaging), carried on delta unless ``AI_PORTFOLIOS_DELTA=1``.

Plus a guard test that every Phase-1 segment slug in the compiled graph has a
matching triage rule, so a future segment can't silently regenerate every run.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: F401 — used for snapshot/injection dict shape

import pytest

from digiquant.olympus.atlas.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.olympus.atlas.triage import evaluate

# A compact onchain-positioning summary shaped like ``compact_summary()`` output
# (overall divergence + a couple of top markets). Equality is what triage tests.
_ONCHAIN_A: dict[str, Any] = {
    "overall_divergence": 0.12,
    "smart_net_bias": 0.61,
    "crowd_net_bias": 0.49,
    "snapshot_ts": "2026-04-26T00:00:00Z",
    "total_traders": 1234,
    "top_divergent_markets": [
        {"market": "BTC", "divergence": 0.31, "smart_bias": 0.7, "crowd_bias": 0.39},
        {"market": "ETH", "divergence": -0.22, "smart_bias": 0.4, "crowd_bias": 0.62},
    ],
}
# A materially different injection (new snapshot_ts + flipped divergence).
_ONCHAIN_B: dict[str, Any] = {
    **_ONCHAIN_A,
    "overall_divergence": -0.30,
    "snapshot_ts": "2026-04-27T00:00:00Z",
}


def _delta_state(
    *,
    onchain_current: dict[str, Any] | None,
    onchain_prior: dict[str, Any] | None,
    run_date: date = date(2026, 4, 27),
    baseline_date: date = date(2026, 4, 26),
) -> AtlasResearchState:
    """Build a delta-run state with the current + prior onchain injections set.

    ``onchain_current`` lands in ``data_layer.market_context`` (what preflight
    injected this run). ``onchain_prior`` lands in the prior snapshot's
    ``onchain_positioning`` slot (what phase6 persisted last run). Either may be
    ``None`` to model a Hyperdash outage on that side.
    """
    market_context: dict[str, Any] = {}
    if onchain_current is not None:
        market_context["onchain_positioning"] = onchain_current
    snapshot: dict[str, Any] = {"bias": "neutral"}
    if onchain_prior is not None:
        snapshot["onchain_positioning"] = onchain_prior
    return AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=baseline_date,
        data_layer=DataLayerSnapshot(
            price_technicals_latest=date(2026, 4, 25),
            price_technicals_ticker_count=56,
            macro_series_latest=date(2026, 4, 25),
            fallback_used="supabase",
            market_context=market_context,
        ),
        prior_context=PriorContext(
            last_snapshots=[
                {
                    "date": baseline_date.isoformat(),
                    "run_type": "baseline",
                    "snapshot": snapshot,
                }
            ]
        ),
    )


def _decision(state: AtlasResearchState, segment: str):
    return next(d for d in evaluate(state).decisions if d.segment == segment)


@pytest.mark.unit
class TestOnchainTriage:
    def test_carries_when_injection_unchanged(self) -> None:
        # Same compact summary this run as last run → near-duplicate of injected
        # data, so the LLM call is skipped.
        state = _delta_state(onchain_current=_ONCHAIN_A, onchain_prior=_ONCHAIN_A)
        d = _decision(state, "alt-onchain-positioning")
        assert d.decision == "carry"
        assert d.tier == "low"
        assert "unchanged" in d.reason

    def test_regenerates_when_injection_changed(self) -> None:
        state = _delta_state(onchain_current=_ONCHAIN_B, onchain_prior=_ONCHAIN_A)
        d = _decision(state, "alt-onchain-positioning")
        assert d.decision == "regenerate"
        assert "changed" in d.reason

    def test_regenerates_when_no_prior_injection(self) -> None:
        # First delta after a run that had no onchain data → no baseline to
        # compare against → conservative regen.
        state = _delta_state(onchain_current=_ONCHAIN_A, onchain_prior=None)
        d = _decision(state, "alt-onchain-positioning")
        assert d.decision == "regenerate"

    def test_regenerates_when_current_injection_absent(self) -> None:
        # Hyperdash outage this run → nothing injected → can't claim "unchanged",
        # regenerate so the segment can record the absence.
        state = _delta_state(onchain_current=None, onchain_prior=_ONCHAIN_A)
        d = _decision(state, "alt-onchain-positioning")
        assert d.decision == "regenerate"


@pytest.mark.unit
class TestAiPortfoliosTriage:
    def test_baseline_run_triages_mandatory_segments(self) -> None:
        # Daily cadence always triages; mandatory tiers still regenerate on baseline.
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        result = evaluate(state)
        assert result.decisions
        macro = next(d for d in result.decisions if d.segment == "macro")
        assert macro.decision == "regenerate"

    def test_delta_carries_without_env(self, monkeypatch) -> None:
        monkeypatch.delenv("AI_PORTFOLIOS_DELTA", raising=False)
        state = _delta_state(onchain_current=_ONCHAIN_A, onchain_prior=_ONCHAIN_A)
        d = _decision(state, "alt-ai-portfolios")
        assert d.decision == "carry"
        assert d.tier == "low"

    def test_delta_regenerates_with_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AI_PORTFOLIOS_DELTA", "1")
        state = _delta_state(onchain_current=_ONCHAIN_A, onchain_prior=_ONCHAIN_A)
        d = _decision(state, "alt-ai-portfolios")
        assert d.decision == "regenerate"
        assert "AI_PORTFOLIOS_DELTA" in d.reason


@pytest.mark.unit
class TestPhase1RuleCoverage:
    def test_every_phase1_segment_has_a_triage_rule(self) -> None:
        # The compiled Phase-1 fan-out and the triage rule table must agree:
        # no Phase-1 segment may be missing a rule (a missing rule means it
        # silently regenerates every delta, the bug #929 fixes).
        state = _delta_state(onchain_current=_ONCHAIN_A, onchain_prior=_ONCHAIN_A)
        triaged = {d.segment for d in evaluate(state).decisions}
        phase1_segments = {spec.segment_slug for spec in ALT_SPECS}
        missing = phase1_segments - triaged
        assert not missing, f"Phase-1 segments missing a triage rule: {sorted(missing)}"
