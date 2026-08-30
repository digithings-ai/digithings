"""Golden-file digest rendering per tier (Observer has no weights/NAV/fills)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.notify.digest import build_digest_content
from digiquant.notify.dispatch import _render_daily_digest
from digiquant.notify.entitlements import PlanTier
from digiquant.notify.mailgun import MailgunConfig

from tests.dq.notify.conftest import FakeSupabase

pytestmark = pytest.mark.unit

_CONFIG = MailgunConfig(
    api_key="key",
    domain="mg.example.com",
    from_address="notify@example.com",
    unsubscribe_base="https://example.com/settings/notifications",
)

_SNAPSHOT = {
    "regime": {
        "bias": "risk-on",
        "label": "Growth",
        "conviction": "medium",
        "summary": "Macro steady.",
    },
    "actionable_summary": ["Watch tech earnings"],
    "risk_radar": ["Rates volatility"],
    "narrative": {"macro": "Fed on hold.", "us_equities": "Breadth improving."},
}

_POSITIONS = [
    {"ticker": "SPY", "weight_pct": 40.0},
    {"ticker": "TLT", "weight_pct": 20.0},
]

_NAV = {"nav": 1050000.12, "day_return_pct": 0.45}
_METRICS = {"attempt_count": 12, "research_spend_usd": 3.5}


def _store() -> FakeSupabase:
    return FakeSupabase(
        tables={
            "daily_snapshots": [{"date": "2026-08-30", "snapshot": _SNAPSHOT}],
            "positions": [
                {**row, "workspace_id": "ws-1", "date": "2026-08-30"} for row in _POSITIONS
            ],
            "nav_history": [{"workspace_id": "ws-1", "date": "2026-08-30", **_NAV}],
            "portfolio_metrics": [{"workspace_id": "ws-1", "date": "2026-08-30", **_METRICS}],
        }
    )


_OBSERVER_FORBIDDEN = (
    "House Weights",
    "NAV:",
    "Pipeline attempts",
    "Research spend",
    "Weight delta",
    "Execution alert",
    "broker_order",
    "fingerprint",
    "api_key",
)


@pytest.mark.parametrize(
    "tier,forbidden,required",
    [
        (PlanTier.FREE, _OBSERVER_FORBIDDEN, ("Market Regime", "Research Narrative")),
        (
            PlanTier.BASELINE,
            ("fingerprint", "api_key", "broker_order"),
            ("House Weights", "NAV:", "Pipeline attempts"),
        ),
        (
            PlanTier.CUSTOM,
            ("fingerprint", "api_key"),
            ("House Weights", "NAV:"),
        ),
    ],
)
def test_digest_golden_per_tier(
    tier: PlanTier,
    forbidden: tuple[str, ...],
    required: tuple[str, ...],
) -> None:
    sb = _store()
    content = build_digest_content(
        sb,
        workspace_id="ws-1",
        tier=tier,
        run_date=date(2026, 8, 30),
        mailgun_config=_CONFIG,
        workspace_name="House",
    )
    text, html = _render_daily_digest(content)
    combined = text + "\n" + html
    for token in forbidden:
        assert token not in combined, f"{tier}: forbidden token {token!r} in output"
    for token in required:
        assert token in combined, f"{tier}: expected token {token!r} missing"
