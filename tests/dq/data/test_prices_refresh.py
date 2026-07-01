"""On-demand technicals recompute (Pillar 1F).

recompute_technicals_from_history reads raw OHLCV from price_history (look-ahead-guarded),
recomputes indicators, and upserts price_technicals — network-free. Tickers below MIN_BARS
are skipped; the read is bounded by .lte(as_of).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from digiquant.data.prices import refresh
from digiquant.data.prices.technicals import MIN_BARS

pytestmark = pytest.mark.unit

AS_OF = date(2026, 3, 1)


def _ohlcv(ticker: str, n: int) -> list[dict]:
    rows = []
    for i in range(n):
        d = date(2026, 1, 1) + timedelta(days=i)
        px = 100.0 + i * 0.5
        rows.append(
            {
                "date": d.isoformat(),
                "ticker": ticker,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + 0.5,
                "volume": 1_000_000,
            }
        )
    return rows


def _capture_upsert():
    seen: dict[str, list] = {}

    def _fake(_client, rows, **_kw):
        seen["rows"] = rows
        return SimpleNamespace(table="price_technicals", rows=len(rows))

    return seen, _fake


def test_recompute_upserts_for_sufficient_history() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 40)),
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF
        )
    assert result.tickers_processed == 1
    assert result.rows_upserted > 0
    assert {"date", "ticker"} <= set(seen["rows"][0])


def test_skips_tickers_below_min_bars() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", MIN_BARS - 1)),
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF
        )
    assert result.tickers_processed == 0
    assert result.rows_upserted == 0
    assert seen["rows"] == []  # upsert called with nothing


def test_empty_tickers_is_noop() -> None:
    with patch.object(refresh, "upsert_price_technicals") as upsert:
        result = refresh.recompute_technicals_from_history(client=object(), tickers=[], as_of=AS_OF)
    assert result == refresh.RefreshResult(0, 0)
    upsert.assert_not_called()


def test_dedupes_tickers_before_read() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 40)) as read,
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY", "SPY", ""], as_of=AS_OF
        )
    # Deduped + empties dropped → a single "SPY" passed to the read.
    assert read.call_args.args[1] == ["SPY"]


def test_read_is_look_ahead_guarded() -> None:
    client = MagicMock()
    chain = client.table.return_value.select.return_value.in_.return_value.lte.return_value.gte.return_value.order.return_value
    chain.execute.return_value.data = []
    refresh.recompute_technicals_from_history(client=client, tickers=["SPY"], as_of=AS_OF)
    client.table.assert_called_with("price_history")
    # The upper bound is run_date — a future price row can never enter the window.
    client.table.return_value.select.return_value.in_.return_value.lte.assert_called_with(
        "date", AS_OF.isoformat()
    )
