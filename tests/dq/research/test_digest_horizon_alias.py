"""Digest risk-radar ``horizon_hourse`` alias (house GHA 33426508863)."""

from __future__ import annotations

import pytest
from digiquant.research.phases.phase7_synthesis import RiskItem
from digiquant.research.snapshot import DigestPayload
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _digest(**radar: object) -> dict[str, object]:
    return {
        "segment": "master-digest",
        "date": "2026-08-31",
        "bias": "neutral",
        "headline": "Test",
        "market_regime_snapshot": "Growth slowing",
        "alt_data_dashboard": "Neutral",
        "institutional_summary": "Flows flat",
        "asset_classes_summary": "Mixed",
        "us_equities_summary": "Narrow breadth",
        "risk_radar": [radar],
    }


def test_horizon_hourse_typo_maps_to_horizon_hours() -> None:
    """Live digest edit merge failed on ``horizon_hourse`` and fell back to full."""
    item = RiskItem.model_validate(
        {
            "horizon_hourse": 72,
            "label": "Breadth fade",
            "trigger": "Three consecutive daily breadth prints.",
        }
    )
    assert item.horizon_hours == 72
    assert item.label == "Breadth fade"


def test_canonical_horizon_hours_still_validates() -> None:
    item = RiskItem.model_validate(
        {"horizon_hours": 24, "label": "FOMC", "trigger": "Minutes drop."}
    )
    assert item.horizon_hours == 24


def test_snapshot_mirror_accepts_the_same_typo() -> None:
    item = RiskItem.model_validate(
        {"horizon_hourse": 48, "label": "CPI", "trigger": "Core above 0.3%."}
    )
    assert item.horizon_hours == 48
    payload = DigestPayload.model_validate(_digest(horizon_hourse=36, label="NFP", trigger="Miss."))
    assert payload.risk_radar[0].horizon_hours == 36


def test_alias_overwrites_stale_canonical_on_dual_key_merge() -> None:
    """Edit merge can leave both keys; the typo is the newly patched value."""
    item = RiskItem.model_validate(
        {
            "horizon_hours": 24,
            "horizon_hourse": 72,
            "label": "Breadth fade",
            "trigger": "Three consecutive daily breadth prints.",
        }
    )
    assert item.horizon_hours == 72
    item2 = RiskItem.model_validate(
        {
            "horizon_hours": 24,
            "horizon_hourse": 48,
            "label": "CPI",
            "trigger": "Core above 0.3%.",
        }
    )
    assert item2.horizon_hours == 48


def test_missing_horizon_still_rejected() -> None:
    with pytest.raises(ValidationError, match="horizon_hours"):
        RiskItem.model_validate({"label": "No horizon", "trigger": "Missing."})
