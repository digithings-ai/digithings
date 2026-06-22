"""Ticker fingerprint unit tests (#925 extension, PR 4b)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PriorContext
from digiquant.olympus.hermes.ticker_fingerprint import (
    deliberation_skip_signal,
    news_hash_for_ticker,
    ticker_triage_signal,
)


@pytest.mark.unit
class TestTickerFingerprint:
    def test_no_prior_returns_none_for_full(self) -> None:
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
        )
        assert ticker_triage_signal(state, "AAPL", current_stance=None, prior_stance=None) is None

    def test_quiet_price_and_stance_returns_skip(self) -> None:
        news = news_hash_for_ticker(
            AtlasResearchState(
                run_type="delta",
                run_date=date(2026, 6, 20),
                config=AtlasConfigBundle(watchlist=["AAPL"]),
            ),
            "AAPL",
        )
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            prior_context=PriorContext(
                prior_analyst_by_ticker={"AAPL": {"stance": "hold", "fingerprint_news_hash": news}}
            ),
            price_deltas={"AAPL": 0.001},
        )
        signal = ticker_triage_signal(
            state, "AAPL", current_stance="hold", prior_stance="hold", prior_news_hash=news
        )
        assert signal is not None
        assert signal.mode == "quiet"

    def test_material_price_move_returns_stale(self) -> None:
        news = "deadbeef"
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            prior_context=PriorContext(
                prior_analyst_by_ticker={"AAPL": {"stance": "hold", "fingerprint_news_hash": news}}
            ),
            price_deltas={"AAPL": 0.05},
        )
        signal = ticker_triage_signal(
            state, "AAPL", current_stance="hold", prior_stance="hold", prior_news_hash=news
        )
        assert signal is not None
        assert signal.mode == "stale"

    def test_deliberation_skip_requires_prior_transcript(self) -> None:
        state = AtlasResearchState(
            run_type="delta",
            run_date=date(2026, 6, 20),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            prior_context=PriorContext(
                prior_analyst_by_ticker={"AAPL": {"stance": "hold", "fingerprint_news_hash": "x"}}
            ),
            price_deltas={"AAPL": 0.001},
        )
        assert deliberation_skip_signal(state, "AAPL", analyst_stance="hold") is False
