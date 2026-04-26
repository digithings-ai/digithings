"""Unit tests for digiquant_atlas.phases.preflight."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant_atlas.phases.preflight import PreflightDeps, build_preflight_node
from digiquant_atlas.state import AtlasConfigBundle, AtlasResearchState

from tests.test_supabase_io import FakeSupabaseClient


@pytest.mark.unit
class TestPreflight:
    def _client_with_fresh_data(self, latest: date) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [
                    {"date": latest.isoformat(), "ticker": "SPY"},
                    {"date": latest.isoformat(), "ticker": "QQQ"},
                ],
                "macro_series_observations": [
                    {"obs_date": latest.isoformat()},
                ],
            }
        )

    def test_baseline_run_happy_path(self) -> None:
        run_date = date(2026, 4, 26)
        client = self._client_with_fresh_data(date(2026, 4, 25))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["SPY", "QQQ"]),
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=run_date)

        out = node(state)

        assert out["config"].watchlist == ["SPY", "QQQ"]
        # Fresh data → supabase is source of truth (not fallback).
        assert out["data_layer"].fallback_used == "supabase"
        assert out["data_layer"].price_technicals_latest == date(2026, 4, 25)
        assert out["data_layer"].macro_series_latest == date(2026, 4, 25)

    def test_delta_run_without_baseline_date_raises(self) -> None:
        client = self._client_with_fresh_data(date(2026, 4, 25))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(),
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 4, 27))
        with pytest.raises(ValueError, match="baseline_date"):
            node(state)

    def test_stale_price_technicals_signals_scripts_fallback(self) -> None:
        run_date = date(2026, 4, 26)
        # Latest 6 days old — beyond the default 3-day staleness threshold.
        client = self._client_with_fresh_data(date(2026, 4, 20))
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(),
            price_staleness_days=3,
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=run_date)
        out = node(state)
        assert out["data_layer"].fallback_used == "scripts"

    def test_missing_price_technicals_signals_no_source(self) -> None:
        run_date = date(2026, 4, 26)
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [],
                "macro_series_observations": [],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(),
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=run_date)
        out = node(state)
        assert out["data_layer"].fallback_used == "none"
        assert out["data_layer"].price_technicals_latest is None
