"""Unit tests for digiquant.olympus.atlas.phases.preflight."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from digiquant.data.prices import refresh as refresh_mod
from digiquant.olympus.atlas.phases.preflight import PreflightDeps, build_preflight_node
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


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

    def _stale_deps(self) -> tuple[FakeSupabaseClient, PreflightDeps]:
        client = self._client_with_fresh_data(date(2026, 4, 20))  # 6 days stale
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["SPY"]),
            price_staleness_days=3,
        )
        return client, deps

    def test_on_demand_refresh_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Without ATLAS_REFRESH_ON_DEMAND the stale signal stands and no recompute is attempted.
        monkeypatch.delenv("ATLAS_REFRESH_ON_DEMAND", raising=False)
        _client, deps = self._stale_deps()
        with patch.object(refresh_mod, "recompute_technicals_from_history") as recompute:
            out = build_preflight_node(deps)(
                AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
            )
        recompute.assert_not_called()
        assert out["data_layer"].fallback_used == "scripts"

    def test_on_demand_refresh_clears_fallback_when_now_fresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_REFRESH_ON_DEMAND", "1")
        client, deps = self._stale_deps()
        run_date = date(2026, 4, 26)

        def _fake_recompute(*, client, tickers, as_of):
            # Simulate the upsert: the table is now fresh on the re-probe.
            client.canned_reads["price_technicals"] = [{"date": as_of.isoformat(), "ticker": "SPY"}]
            return SimpleNamespace(tickers_processed=1, rows_upserted=12)

        with patch.object(
            refresh_mod, "recompute_technicals_from_history", side_effect=_fake_recompute
        ):
            out = build_preflight_node(deps)(
                AtlasResearchState(run_type="baseline", run_date=run_date)
            )
        # Refresh brought it current → fallback cleared back to supabase.
        assert out["data_layer"].fallback_used == "supabase"
        assert out["data_layer"].price_technicals_latest == run_date

    def test_on_demand_refresh_is_fail_soft(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_REFRESH_ON_DEMAND", "1")
        _client, deps = self._stale_deps()
        with patch.object(
            refresh_mod,
            "recompute_technicals_from_history",
            side_effect=RuntimeError("supabase down"),
        ):
            out = build_preflight_node(deps)(
                AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
            )
        # Refresh failed → keep the stale data + the scripts signal (never crashes preflight).
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
