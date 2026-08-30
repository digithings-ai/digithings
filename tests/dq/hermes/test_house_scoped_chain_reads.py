"""House GHA Group A reads ignore overlay nav_history / positions / metrics.

Hermes chain (`python -m digiquant.olympus.hermes.chain`) filters
``workspace_id`` on Group A tables so an overlay same-calendar row cannot
seed house NAV, trip the drawdown breaker, or open lots from a private book.
Omitted ``workspace_id`` means house.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from digiquant.olympus.atlas.supabase_io import load_portfolio_performance_snapshot
from digiquant.olympus.hermes.portfolio_materialize import _prior_nav as materialize_prior_nav
from digiquant.olympus.hermes.risk_controls import BreakerConfig, breaker_scale_from_nav_history
from digiquant.olympus.hermes.writers.commit_io import _compute_nav
from digiquant.olympus.hermes.writers.commit_io import _prior_nav as commit_prior_nav
from digiquant.olympus.hermes.writers.opening_snapshot import (
    HOLDING_LOTS,
    cold_start_requires_seed,
    ensure_legacy_opening_snapshot,
)
from digiquant.olympus.tenancy import house_workspace_id

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.hermes.test_opening_snapshot import BOOK_D, NOW, _book_client

pytestmark = pytest.mark.unit

_OVERLAY = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_RUN = date(2026, 7, 31)


def _house() -> str:
    return str(house_workspace_id())


def _overlay() -> str:
    return str(_OVERLAY)


class TestCommitPriorNav:
    def test_house_prior_nav_ignores_later_overlay_row(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-07-29", "nav": 100.0, "workspace_id": _house()},
                    {"date": "2026-07-30", "nav": 999.0, "workspace_id": _overlay()},
                ]
            }
        )
        assert commit_prior_nav(client, _RUN) == pytest.approx(100.0)

    def test_overlay_prior_nav_does_not_read_house(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-07-29", "nav": 100.0, "workspace_id": _house()},
                    {"date": "2026-07-30", "nav": 111.0, "workspace_id": _overlay()},
                ]
            }
        )
        assert commit_prior_nav(client, _RUN, workspace_id=_overlay()) == pytest.approx(111.0)

    def test_compute_nav_flat_when_overlay_is_the_only_later_point(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-07-29", "nav": 100.0, "workspace_id": _house()},
                    {"date": "2026-07-30", "nav": 999.0, "workspace_id": _overlay()},
                ],
                "price_history": [],
            }
        )
        prior_book = [{"date": "2026-07-29", "ticker": "SPY", "weight_pct": 100.0}]
        assert _compute_nav(client, _RUN, prior_book) == pytest.approx(100.0)


class TestMaterializePriorNav:
    def test_house_materialize_prior_nav_ignores_overlay(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-07-29", "nav": 142.0, "workspace_id": _house()},
                    {"date": "2026-07-30", "nav": 1.0, "workspace_id": _overlay()},
                ]
            }
        )
        assert materialize_prior_nav(client, _RUN) == pytest.approx(142.0)


class TestPerformanceSnapshot:
    def test_house_snapshot_ignores_overlay_nav_and_metrics(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {
                        "date": "2026-06-17",
                        "nav": 102.5,
                        "cash_pct": 30,
                        "invested_pct": 70,
                        "workspace_id": _house(),
                    },
                    {
                        "date": "2026-06-18",
                        "nav": 1.0,
                        "cash_pct": 0,
                        "invested_pct": 100,
                        "workspace_id": _overlay(),
                    },
                ],
                "portfolio_metrics": [
                    {
                        "date": "2026-06-17",
                        "pnl_pct": 2.5,
                        "sharpe": 1.1,
                        "volatility": 8.0,
                        "max_drawdown": -3.0,
                        "alpha": 0.4,
                        "workspace_id": _house(),
                    },
                    {
                        "date": "2026-06-18",
                        "pnl_pct": 99.0,
                        "sharpe": 9.9,
                        "volatility": 90.0,
                        "max_drawdown": -90.0,
                        "alpha": 9.9,
                        "workspace_id": _overlay(),
                    },
                ],
            }
        )
        snap = load_portfolio_performance_snapshot(client, date(2026, 6, 19))
        assert snap["nav_date"] == "2026-06-17"
        assert snap["nav"] == 102.5
        assert snap["metrics"]["sharpe"] == 1.1


class TestDrawdownBreaker:
    def test_overlay_crash_does_not_trip_house_breaker(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-06-01", "nav": 100.0, "workspace_id": _house()},
                    {"date": "2026-06-10", "nav": 100.0, "workspace_id": _house()},
                    {"date": "2026-06-10", "nav": 1.0, "workspace_id": _overlay()},
                ]
            }
        )
        state = breaker_scale_from_nav_history(
            client, date(2026, 6, 12), config=BreakerConfig()
        )
        assert state.current_nav == pytest.approx(100.0)
        assert state.scale == 1.0


class TestOpeningSnapshotHouseBook:
    def test_overlay_only_book_does_not_require_house_seed(self) -> None:
        client = _book_client(
            positions=[
                {
                    "ticker": "EVIL",
                    "weight_pct": 100,
                    "date": BOOK_D.isoformat(),
                    "workspace_id": _overlay(),
                }
            ]
        )
        assert cold_start_requires_seed(client=client, book_date=BOOK_D) is False

    def test_house_seed_uses_house_nav_not_overlay_nav(self) -> None:
        client = _book_client(
            positions=[
                {"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()},
                {"ticker": "CASH", "weight_pct": 60, "date": BOOK_D.isoformat()},
            ]
        )
        client.store["nav_history"] = [
            {"date": BOOK_D.isoformat(), "nav": "1", "workspace_id": _overlay()},
            {"date": BOOK_D.isoformat(), "nav": "100000", "workspace_id": _house()},
        ]
        ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
        assert ok is True, reason
        lots = [r for r in client.store[HOLDING_LOTS] if r.get("status") == "open"]
        assert lots, "house NAV 100000 should seed SPY lots; overlay NAV 1 must not win"
        # (40/100)*100000/500 = 80. Overlay NAV 1 would seed ~0.08.
        by_symbol = {r["symbol"]: Decimal(str(r["quantity"])) for r in lots}
        assert by_symbol["SPY"] == Decimal("80.000000")
