"""Unit tests for the deterministic portfolio focus-list selection (#696)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.portfolio.candidates import (
    load_portfolio_holdings,
    score_technicals,
    select_focus_tickers,
)

from tests.dq.research.test_supabase_io import FakeSupabaseClient

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


def _install_technicals(monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
    """Stub the R2 technicals batch seam (#4053, #4600) — R2-only now."""
    by_ticker = {row["ticker"]: row for row in rows}

    def fake(*, client, tickers, lookback, as_of):
        out: dict[str, dict] = {}
        for ticker in tickers:
            latest = by_ticker.get(ticker) or by_ticker.get(ticker.upper(), {})
            out[ticker] = {
                "ticker": ticker,
                "latest": latest,
                "window": [latest] if latest else [],
            }
        return out

    monkeypatch.setattr("digiquant.research.data.queries.get_price_technicals_batch", fake)


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
    def test_top_scored_candidates_selected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rows = [
            _row("WIN", roc_21=9.0, adx_14=30.0),
            _row("MID", roc_21=2.0),
            _row("LOSE", pct_vs_sma50=-3.0, pct_vs_sma200=-5.0, roc_21=-8.0),
        ]
        _install_technicals(monkeypatch, rows)
        focus = select_focus_tickers(
            client=_client(rows),
            watchlist=["LOSE", "MID", "WIN"],
            run_date=RUN_DATE,
            top_n=2,
        )
        # Holdings (from config/portfolio.json) lead; scored candidates follow.
        scored = [t for t in focus if t in ("WIN", "MID", "LOSE")]
        assert scored == ["WIN", "MID"]

    def test_holdings_always_included_and_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        holdings = load_portfolio_holdings()
        assert holdings, "config/portfolio.json should declare positions"
        _install_technicals(monkeypatch, [_row("WIN")])
        focus = select_focus_tickers(
            client=_client([_row("WIN")]),
            watchlist=["WIN"],
            run_date=RUN_DATE,
            top_n=1,
        )
        assert focus[: len(holdings)] == holdings

    def test_fails_soft_to_watchlist_head(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Exploding(FakeSupabaseClient):
            def table(self, name: str):  # duck-typed fake
                raise RuntimeError("boom")

        def _boom(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("digiquant.research.data.queries.get_price_technicals_batch", _boom)
        focus = select_focus_tickers(
            client=_Exploding(canned_reads={}),
            watchlist=["A", "B", "C"],
            run_date=RUN_DATE,
            top_n=2,
        )
        assert "A" in focus and "B" in focus

    def test_tickers_without_technicals_are_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_technicals(monkeypatch, [_row("KNOWN")])
        focus = select_focus_tickers(
            client=_client([_row("KNOWN")]),
            watchlist=["KNOWN", "UNKNOWN"],
            run_date=RUN_DATE,
            top_n=5,
        )
        assert "KNOWN" in focus
        assert "UNKNOWN" not in focus

    def test_duplicate_watchlist_entries_are_deduped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_technicals(monkeypatch, [_row("WIN")])
        focus = select_focus_tickers(
            client=_client([_row("WIN")]),
            watchlist=["WIN", "WIN", "WIN"],
            run_date=RUN_DATE,
            top_n=3,
        )
        assert focus.count("WIN") == 1

    def test_top_n_zero_skips_scoring_and_returns_holdings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _MustNotQuery(FakeSupabaseClient):
            def table(self, name: str):  # duck-typed fake
                raise AssertionError("scoring query should not run when top_n=0")

        def _must_not_run(**kwargs):
            raise AssertionError("scoring query should not run when top_n=0")

        monkeypatch.setattr(
            "digiquant.research.data.queries.get_price_technicals_batch", _must_not_run
        )
        focus = select_focus_tickers(
            client=_MustNotQuery(canned_reads={}),
            watchlist=["A", "B"],
            run_date=RUN_DATE,
            top_n=0,
        )
        assert focus == load_portfolio_holdings()

    def test_scoring_uses_one_batch_call_not_one_per_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#4600: the whole candidate pool is fetched in one batch call."""
        calls: list[list[str]] = []

        def _counting_batch(*, client, tickers, lookback, as_of):
            calls.append(list(tickers))
            return {t: {"ticker": t, "latest": _row(t), "window": [_row(t)]} for t in tickers}

        monkeypatch.setattr(
            "digiquant.research.data.queries.get_price_technicals_batch", _counting_batch
        )
        focus = select_focus_tickers(
            client=object(),
            watchlist=["A", "B", "C", "D"],
            run_date=RUN_DATE,
            top_n=2,
            holdings=[],
        )
        assert calls == [["A", "B", "C", "D"]]
        assert focus == ["A", "B"]
