"""R2 market-data freshness gate (#4013): a silent universe drop must fail loud."""

from __future__ import annotations

from datetime import UTC, datetime

from digiquant.research.data.queries import r2_manifest_seal


def assert_market_data_fresh(*, max_age_days: int = 1, min_tickers: int = 100) -> None:
    seal, tickers = r2_manifest_seal()
    age = (datetime.now(UTC).date() - seal).days
    if age > max_age_days:
        raise RuntimeError(f"R2 market data is stale: seal {seal.isoformat()} is {age}d old")
    if tickers < min_tickers:
        raise RuntimeError(f"R2 market data universe collapsed: {tickers} tickers < {min_tickers}")
