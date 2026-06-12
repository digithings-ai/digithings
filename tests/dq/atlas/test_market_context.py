"""Unit tests for the deterministic market-context injection (#694).

Research agents never invoke the Supabase data tools (tool_choice=auto), so
preflight injects a compact latest-values block into ``DataLayerSnapshot``,
which ``_shared_context`` already serializes into every phase call.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.data.queries import get_market_context
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    _market_context_tickers,
    build_preflight_node,
)
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)


def _client(price_rows=None, macro_rows=None) -> FakeSupabaseClient:
    return FakeSupabaseClient(
        canned_reads={
            "daily_snapshots": [],
            "documents": [],
            "price_technicals": price_rows
            or [
                {"date": "2026-06-11", "ticker": "SPY", "rsi_14": 61.2, "pct_vs_sma50": 2.1},
                {"date": "2026-06-10", "ticker": "SPY", "rsi_14": 58.0, "pct_vs_sma50": 1.7},
                {"date": "2026-06-11", "ticker": "TLT", "rsi_14": 44.5, "pct_vs_sma50": -0.8},
            ],
            "macro_series_observations": macro_rows
            or [
                {"series_id": "DGS10", "obs_date": "2026-06-11", "value": 4.21, "unit": "pct"},
                {"series_id": "DGS10", "obs_date": "2026-06-10", "value": 4.18, "unit": "pct"},
            ],
        }
    )


class TestGetMarketContext:
    def test_latest_row_per_ticker_wins(self) -> None:
        ctx = get_market_context(
            client=_client(),
            tickers=["SPY", "TLT", "MISSING"],
            series_ids=[],
            run_date=RUN_DATE,
        )
        assert ctx["as_of"] == "2026-06-12"
        assert ctx["price_technicals"]["SPY"]["rsi_14"] == 61.2
        assert ctx["price_technicals"]["SPY"]["date"] == "2026-06-11"
        assert ctx["price_technicals"]["TLT"]["rsi_14"] == 44.5
        # Tickers absent from the table are omitted, not nulled.
        assert "MISSING" not in ctx["price_technicals"]

    def test_macro_series_latest_and_prev(self) -> None:
        ctx = get_market_context(
            client=_client(),
            tickers=[],
            series_ids=["DGS10"],
            run_date=RUN_DATE,
        )
        dgs10 = ctx["macro_series"]["DGS10"]
        assert dgs10["value"] == 4.21
        assert dgs10["prev_value"] == 4.18
        assert dgs10["date"] == "2026-06-11"

    def test_empty_inputs_yield_empty_blocks(self) -> None:
        ctx = get_market_context(client=_client(), tickers=[], series_ids=[], run_date=RUN_DATE)
        assert ctx["price_technicals"] == {}
        assert ctx["macro_series"] == {}


class TestMarketContextTickers:
    def test_includes_core_set_and_sector_etfs(self) -> None:
        tickers = _market_context_tickers()
        assert "SPY" in tickers
        assert "TLT" in tickers
        # Sector headline ETFs come from config/sectors.yaml.
        assert "XLK" in tickers
        # No duplicates.
        assert len(tickers) == len(set(tickers))


class TestPreflightInjection:
    def test_preflight_populates_market_context(self) -> None:
        deps = PreflightDeps(
            client=_client(),
            config_loader=lambda: AtlasConfigBundle(watchlist=["SPY"], macro_series=["DGS10"]),
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=RUN_DATE)

        out = node(state)

        mc = out["data_layer"].market_context
        assert mc["price_technicals"]["SPY"]["rsi_14"] == 61.2
        assert mc["macro_series"]["DGS10"]["value"] == 4.21

    def test_preflight_fails_soft_when_market_context_query_raises(self) -> None:
        # Explode only on the per-series `.eq("series_id", …)` filter, which is
        # unique to get_market_context's macro path — the freshness probes
        # (no eq) must keep working.
        class _ExplodingClient(FakeSupabaseClient):
            def table(self, name: str):  # noqa: ANN201 — duck-typed fake
                query = super().table(name)
                if name == "macro_series_observations":

                    def _boom(_col: str, _val: object) -> None:
                        raise RuntimeError("boom")

                    query.eq = _boom  # type: ignore[method-assign]
                return query

        deps = PreflightDeps(
            client=_ExplodingClient(
                canned_reads={
                    "daily_snapshots": [],
                    "documents": [],
                    "price_technicals": [{"date": "2026-06-11", "ticker": "SPY"}],
                    "macro_series_observations": [{"obs_date": "2026-06-11"}],
                }
            ),
            config_loader=lambda: AtlasConfigBundle(macro_series=["DGS10"]),
        )
        node = build_preflight_node(deps)
        out = node(AtlasResearchState(run_type="baseline", run_date=RUN_DATE))

        # Freshness metadata survives; market_context degrades to empty.
        assert out["data_layer"].price_technicals_latest == date(2026, 6, 11)
        assert out["data_layer"].market_context == {}
