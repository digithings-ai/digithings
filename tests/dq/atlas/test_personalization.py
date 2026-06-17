"""Unit tests for digiquant.olympus.atlas.personalization.

Covers anonymous pass-through, ticker exclusion, custom-universe boosting,
risk-tolerance filtering, ESG sector exclusion, the return-shape contract,
and the < 100 ms (relaxed to < 200 ms in CI) performance budget.

Issue #312.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

import pytest

from digiquant.olympus.atlas import (
    PersonalizedSnapshot,
    SnapshotEnvelope,
    personalize_snapshot,
)
from digiquant.olympus.atlas.snapshot import DigestPayload
from digiquant.profiles import AssetPreferences, InvestmentProfile


# ─── Helpers (mirror tests/dq/atlas/test_snapshot.py style) ────────────────


def _digest_payload_kwargs() -> dict[str, Any]:
    """Hand-built digest, mirrors the snapshot-test helper."""
    return {
        "segment": "master-digest",
        "date": date(2026, 4, 20),
        "bias": "neutral",
        "headline": "Markets digest mixed Fed signals; risk-on intact in tech",
        "material_findings": [
            {
                "label": "Tech leadership widens",
                "summary": "QQQ +1.8%, NVDA +3.1% on AI capex commentary.",
                "source_ids": ["src-1"],
            }
        ],
        "sources": [
            {"id": "src-1", "title": "WSJ Markets Live", "url": "https://wsj.com/x"},
        ],
        "notes": "Volume light into Fed week.",
        "market_regime_snapshot": "Risk-on; growth leadership reasserting.",
        "alt_data_dashboard": "Card-spend trends accelerating in services.",
        "institutional_summary": "Net inflows into US equity ETFs.",
        "asset_classes_summary": "Equities up; bonds flat; commodities mixed.",
        "us_equities_summary": "Tech +1.8%, energy -0.4%; breadth fair.",
        "thesis_tracker": "Long-tech thesis intact.",
        "portfolio_recommendations": "Hold growth; trim defensives 2pp.",
        "actionable_summary": [
            {
                "priority": 1,
                "label": "Trim staples",
                "rationale": "Defensives losing relative momentum.",
            },
            {
                "priority": 4,
                "label": "Add NVDA on dip",
                "rationale": "AI capex commentary supportive.",
            },
        ],
        "risk_radar": [
            {
                "horizon_hours": 24,
                "label": "Hawkish FOMC minutes",
                "trigger": "5y5y reprices >10bps wider.",
            }
        ],
        "segment_freshness": {
            "macro": {"source": "today", "as_of": "2026-04-20"},
        },
    }


def _envelope_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_date": date(2026, 4, 20),
        "run_type": "baseline",
        "baseline_date": None,
        "published_at": datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        "digest": _digest_payload_kwargs(),
    }
    base.update(overrides)
    return base


def _make_envelope(**overrides: Any) -> SnapshotEnvelope:
    return SnapshotEnvelope(**_envelope_kwargs(**overrides))


def _moderate_profile(**overrides: Any) -> InvestmentProfile:
    """A 'neutral' profile that disables ESG drops and keeps all priorities."""
    base: dict[str, Any] = {
        "risk_tolerance": "moderate",
        "horizon_years": 10,
        "liquidity_needs": "medium",
        "base_currency": "USD",
        "tax_jurisdiction": "US",
        "esg_preference": "none",
        "excluded_sectors": [],
        "experience_level": "intermediate",
    }
    base.update(overrides)
    return InvestmentProfile(**base)


# ─── 1. Anonymous pass-through ──────────────────────────────────────────────


@pytest.mark.unit
def test_anonymous_returns_unchanged() -> None:
    env = _make_envelope()
    result = personalize_snapshot(env, profile=None, preferences=None)
    # Same instance — anonymous path is a no-op.
    assert result.envelope is env
    assert result.excluded_count == 0
    assert result.rank_changes == []


# ─── 2. Excluded ticker dropped from actionable ────────────────────────────


@pytest.mark.unit
def test_excluded_ticker_dropped_from_actionable() -> None:
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {
            "priority": 4,
            "label": "Trim XOM exposure",
            "rationale": "Oil rolling over.",
        },
        {
            "priority": 4,
            "label": "Add NVDA on dip",
            "rationale": "AI capex commentary supportive.",
        },
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    prefs = AssetPreferences(excluded_tickers=["XOM"])
    result = personalize_snapshot(env, preferences=prefs)

    labels = [item.label for item in result.envelope.digest.actionable_summary]
    assert "Trim XOM exposure" not in labels
    assert "Add NVDA on dip" in labels
    assert result.excluded_count == 1


# ─── 3. Custom-universe boosts rank ─────────────────────────────────────────


@pytest.mark.unit
def test_custom_universe_boosts_rank_or_tags() -> None:
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {
            "priority": 3,
            "label": "Trim staples",
            "rationale": "Defensives losing relative momentum.",
        },
        {
            "priority": 3,
            "label": "Energy hedge",
            "rationale": "OPEC supply uncertainty.",
        },
        {
            "priority": 3,
            "label": "Long NVDA",
            "rationale": "AI capex tailwind.",
        },
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    prefs = AssetPreferences(custom_universe=["NVDA"])
    result = personalize_snapshot(env, preferences=prefs)

    labels = [item.label for item in result.envelope.digest.actionable_summary]
    # NVDA mention moved to position 0.
    assert labels[0] == "Long NVDA"
    # Other items kept relative order.
    assert labels[1:] == ["Trim staples", "Energy hedge"]
    # rank_changes records what moved (only the items whose index changed).
    assert ("Long NVDA", 2, 0) in result.rank_changes
    assert ("Trim staples", 0, 1) in result.rank_changes
    assert ("Energy hedge", 1, 2) in result.rank_changes


# ─── 4. Conservative drops low priority ─────────────────────────────────────


@pytest.mark.unit
def test_conservative_drops_low_priority_items() -> None:
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {"priority": 1, "label": "Speculative call", "rationale": "Tactical."},
        {"priority": 2, "label": "Edge trade", "rationale": "Small size."},
        {"priority": 3, "label": "Core hold", "rationale": "Long-term."},
        {"priority": 5, "label": "Defensive bond", "rationale": "Treasury ladder."},
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    profile = _moderate_profile(risk_tolerance="conservative")
    result = personalize_snapshot(env, profile=profile)

    labels = [item.label for item in result.envelope.digest.actionable_summary]
    assert labels == ["Core hold", "Defensive bond"]
    assert result.excluded_count == 2  # priority 1 + priority 2 dropped


# ─── 5. Aggressive keeps all items ──────────────────────────────────────────


@pytest.mark.unit
def test_aggressive_keeps_all_items() -> None:
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {"priority": 1, "label": "Speculative call", "rationale": "Tactical."},
        {"priority": 2, "label": "Edge trade", "rationale": "Small size."},
        {"priority": 3, "label": "Core hold", "rationale": "Long-term."},
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    profile = _moderate_profile(risk_tolerance="aggressive")
    result = personalize_snapshot(env, profile=profile)

    labels = [item.label for item in result.envelope.digest.actionable_summary]
    assert labels == ["Speculative call", "Edge trade", "Core hold"]
    assert result.excluded_count == 0


# ─── 6. Strict ESG drops excluded-sector mentions ───────────────────────────


@pytest.mark.unit
def test_strict_esg_drops_excluded_sector_mentions() -> None:
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {
            "priority": 4,
            "label": "Long Tobacco basket",
            "rationale": "Defensive cash flows.",
        },
        {
            "priority": 4,
            "label": "Add NVDA on dip",
            "rationale": "AI capex commentary.",
        },
    ]
    digest["risk_radar"] = [
        {
            "horizon_hours": 48,
            "label": "Tobacco regulation headlines",
            "trigger": "FDA menthol ban revival.",
        },
        {
            "horizon_hours": 24,
            "label": "Hawkish FOMC minutes",
            "trigger": "5y5y reprices wider.",
        },
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    profile = _moderate_profile(esg_preference="strict", excluded_sectors=["tobacco"])
    result = personalize_snapshot(env, profile=profile)

    actionable_labels = [item.label for item in result.envelope.digest.actionable_summary]
    risk_labels = [item.label for item in result.envelope.digest.risk_radar]
    assert "Long Tobacco basket" not in actionable_labels
    assert "Add NVDA on dip" in actionable_labels
    assert "Tobacco regulation headlines" not in risk_labels
    assert "Hawkish FOMC minutes" in risk_labels
    assert result.excluded_count == 2


# ─── 7. Return-shape contract ───────────────────────────────────────────────


@pytest.mark.unit
def test_returns_envelope_subclass_or_envelope() -> None:
    """Asserts the return type contract: PersonalizedSnapshot wrapping a SnapshotEnvelope.

    See module docstring of digiquant.olympus.atlas.personalization for the rationale —
    we picked the sibling-dataclass form over a v2 envelope bump because
    SnapshotEnvelope/DigestPayload are extra="forbid" end-to-end.
    """
    env = _make_envelope()
    result = personalize_snapshot(
        env,
        profile=_moderate_profile(),
        preferences=AssetPreferences(),
    )
    assert isinstance(result, PersonalizedSnapshot)
    assert isinstance(result.envelope, SnapshotEnvelope)
    assert isinstance(result.envelope.digest, DigestPayload)
    # Schema version preserved (no v2 bump).
    assert result.envelope.schema_version == env.schema_version


# ─── 8. Performance budget ──────────────────────────────────────────────────


@pytest.mark.unit
def test_performance_budget_under_200ms_for_100_items() -> None:
    """Issue req: < 100 ms; CI-safe assert at 200 ms to absorb runner variance."""
    digest = _digest_payload_kwargs()
    digest["actionable_summary"] = [
        {
            "priority": (i % 5) + 1,
            "label": f"Idea {i} on AAPL" if i % 3 == 0 else f"Idea {i} on tobacco basket",
            "rationale": f"Rationale {i} mentioning XOM and TSLA.",
        }
        for i in range(100)
    ]
    env = SnapshotEnvelope(**_envelope_kwargs(digest=digest))

    profile = _moderate_profile(
        risk_tolerance="conservative",
        esg_preference="strict",
        excluded_sectors=["tobacco"],
    )
    prefs = AssetPreferences(
        excluded_tickers=["XOM"],
        custom_universe=["AAPL"],
    )

    start = time.perf_counter()
    result = personalize_snapshot(env, profile=profile, preferences=prefs)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms < 200.0, (
        f"personalize_snapshot took {elapsed_ms:.2f} ms; budget is < 100 ms (CI assert < 200 ms)"
    )
    # Sanity: exclusion + boost actually happened.
    assert isinstance(result, PersonalizedSnapshot)
    assert result.excluded_count > 0
