"""Unit tests for the deterministic Hermes focus-list selection (#696)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.hermes.candidates import (
    load_portfolio_holdings,
    score_technicals,
    select_focus_tickers,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)


def _client(rows) -> FakeSupabaseClient:
    return FakeSupabaseClient(canned_reads={"price_technicals": rows})


def _row(ticker: str, **overrides):
    base = {
        "date": "2026-06-11",
        "ticker": ticker,
        "pct_vs_sma50": 1.0,
        "pct_vs_sma200": 1.0,
        "roc_21": 0.0,
        "adx_14": 20.0,
        "rsi_14": 55.0,
    }
    base.update(overrides)
    return base


class TestScore:
    def test_trend_and_momentum_rank_higher(self) -> None:
        strong = score_technicals(_row("A", roc_21=8.0, adx_14=30.0))
        weak = score_technicals(_row("B", pct_vs_sma50=-1.0, pct_vs_sma200=-2.0, roc_21=-6.0))
        assert strong > weak

    def test_stretched_rsi_is_penalized(self) -> None:
        calm = score_technicals(_row("A", rsi_14=60.0))
        stretched = score_technicals(_row("A", rsi_14=82.0))
        assert calm > stretched

    def test_momentum_contribution_is_clamped(self) -> None:
        assert score_technicals(_row("A", roc_21=100.0)) == score_technicals(_row("A", roc_21=10.0))

    def test_tolerates_missing_fields(self) -> None:
        assert score_technicals({"ticker": "A"}) == 0.0


class TestSelectFocusTickers:
    def test_top_scored_candidates_selected(self) -> None:
        rows = [
            _row("WIN", roc_21=9.0, adx_14=30.0),
            _row("MID", roc_21=2.0),
            _row("LOSE", pct_vs_sma50=-3.0, pct_vs_sma200=-5.0, roc_21=-8.0),
        ]
        focus = select_focus_tickers(
            client=_client(rows),
            watchlist=["LOSE", "MID", "WIN"],
            run_date=RUN_DATE,
            top_n=2,
        )
        # Holdings (from config/portfolio.json) lead; scored candidates follow.
        scored = [t for t in focus if t in ("WIN", "MID", "LOSE")]
        assert scored == ["WIN", "MID"]

    def test_holdings_always_included_and_first(self) -> None:
        holdings = load_portfolio_holdings()
        assert holdings, "config/portfolio.json should declare positions"
        focus = select_focus_tickers(
            client=_client([_row("WIN")]),
            watchlist=["WIN"],
            run_date=RUN_DATE,
            top_n=1,
        )
        assert focus[: len(holdings)] == holdings

    def test_fails_soft_to_watchlist_head(self) -> None:
        class _Exploding(FakeSupabaseClient):
            def table(self, name: str):  # noqa: ANN201 — duck-typed fake
                raise RuntimeError("boom")

        focus = select_focus_tickers(
            client=_Exploding(canned_reads={}),
            watchlist=["A", "B", "C"],
            run_date=RUN_DATE,
            top_n=2,
        )
        assert "A" in focus and "B" in focus

    def test_tickers_without_technicals_are_skipped(self) -> None:
        focus = select_focus_tickers(
            client=_client([_row("KNOWN")]),
            watchlist=["KNOWN", "UNKNOWN"],
            run_date=RUN_DATE,
            top_n=5,
        )
        assert "KNOWN" in focus
        assert "UNKNOWN" not in focus
