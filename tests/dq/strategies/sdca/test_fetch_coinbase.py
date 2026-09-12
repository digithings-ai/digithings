"""Unit tests for scripts/fetch_coinbase.py's CCXT pagination + bar conversion.

Exercised against a fake CCXT-shaped exchange (no network) so the timeframe
generalization (arbitrary CCXT timeframe + explicit end date, instead of a
hardcoded daily-ms pagination step) stays covered without live Coinbase
calls.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any  # score:allow untyped any — fake CCXT exchange call log

import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("ccxt")

_SCRIPT_PATH = Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "fetch_coinbase.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_coinbase", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_script()


def _bar(ts_ms: int, *, close: float = 100.0) -> list:
    return [ts_ms, close, close + 1, close - 1, close, 10.0]


class _FakeExchange:
    """Minimal CCXT-shaped fake: parse8601/parse_timeframe + scripted fetch_ohlcv pages."""

    def __init__(
        self, *, pages: list[list[list]], timeframe_seconds: dict[str, int] | None = None
    ) -> None:
        self._pages = list(pages)
        self._timeframe_seconds = timeframe_seconds or {"1d": 86400, "1h": 3600}
        self.rateLimit = 0
        self.calls: list[dict[str, Any]] = []

    def parse_timeframe(self, timeframe: str) -> int:
        return self._timeframe_seconds[timeframe]

    def parse8601(self, iso: str) -> int:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)

    def fetch_ohlcv(self, symbol: str, timeframe: str, *, since: int, limit: int) -> list[list]:
        self.calls.append(
            {"symbol": symbol, "timeframe": timeframe, "since": since, "limit": limit}
        )
        if self._pages:
            return self._pages.pop(0)
        return []


class TestFetchAllDaily:
    def test_paginates_daily_bars_until_now(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_MODULE.time, "sleep", lambda _s: None)
        monkeypatch.setattr(
            _MODULE.time, "time", lambda: datetime(2020, 1, 3, tzinfo=timezone.utc).timestamp()
        )
        day0 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        day1 = day0 + 86_400_000
        exchange = _FakeExchange(pages=[[_bar(day0), _bar(day1)], []])
        bars = _MODULE.fetch_all_daily(exchange, "BTC/USD", "2020-01-01")
        assert [b[0] for b in bars] == [day0, day1]

    def test_end_param_bounds_pagination_and_uses_daily_timeframe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_MODULE.time, "sleep", lambda _s: None)
        day0 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        exchange = _FakeExchange(pages=[[_bar(day0)]])
        bars = _MODULE.fetch_all_daily(exchange, "BTC/USD", "2020-01-01", end="2020-01-02")
        assert len(bars) == 1
        assert exchange.calls[0]["timeframe"] == "1d"

    def test_non_daily_timeframe_is_forwarded_to_fetch_ohlcv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_MODULE.time, "sleep", lambda _s: None)
        hour0 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        exchange = _FakeExchange(pages=[[_bar(hour0)]])
        _MODULE.fetch_all_daily(exchange, "BTC/USD", "2020-01-01", timeframe="1h", end="2020-01-02")
        assert exchange.calls[0]["timeframe"] == "1h"

    def test_empty_page_advances_since_by_batch_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_MODULE.time, "sleep", lambda _s: None)
        start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
        day0 = int(start_date.timestamp() * 1000)
        skip_to = day0 + 300 * 86_400_000
        end_date = (start_date + timedelta(days=301)).date().isoformat()
        exchange = _FakeExchange(pages=[[], [_bar(skip_to)]])
        bars = _MODULE.fetch_all_daily(exchange, "BTC/USD", "2020-01-01", end=end_date)
        assert exchange.calls[0]["since"] == day0
        assert exchange.calls[1]["since"] == skip_to
        assert len(bars) == 1


class TestBarsToPolars:
    def test_daily_timeframe_uses_date_only_timestamp(self) -> None:
        ts_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        df = _MODULE.bars_to_polars([_bar(ts_ms)], "BTC-USD")
        assert df["timestamp"][0] == "2020-01-01"

    def test_non_daily_timeframe_uses_iso_datetime_timestamp(self) -> None:
        ts_ms = int(datetime(2020, 1, 1, 5, 30, tzinfo=timezone.utc).timestamp() * 1000)
        df = _MODULE.bars_to_polars([_bar(ts_ms)], "BTC-USD", timeframe="1h")
        assert df["timestamp"][0] == "2020-01-01T05:30:00Z"

    def test_distinct_intraday_bars_do_not_collide_on_date(self) -> None:
        ts0 = int(datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        ts1 = int(datetime(2020, 1, 1, 1, 0, tzinfo=timezone.utc).timestamp() * 1000)
        df = _MODULE.bars_to_polars([_bar(ts0), _bar(ts1)], "BTC-USD", timeframe="1h")
        assert df["timestamp"].n_unique() == 2

    def test_symbol_column_matches_ticker(self) -> None:
        ts_ms = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        df = _MODULE.bars_to_polars([_bar(ts_ms)], "ETH-USD")
        assert df["symbol"][0] == "ETH-USD"


class TestCachePathFor:
    """Intraday bars must not overwrite the daily price-history cache (#3944)."""

    def test_daily_uses_canonical_ticker_csv(self, tmp_path: Path) -> None:
        assert _MODULE.cache_path_for(tmp_path, "BTC-USD", "1d") == tmp_path / "BTC-USD.csv"

    def test_intraday_uses_timeframe_namespace(self, tmp_path: Path) -> None:
        assert _MODULE.cache_path_for(tmp_path, "BTC-USD", "1h") == tmp_path / "1h" / "BTC-USD.csv"

    def test_intraday_does_not_collide_with_daily_cache(self, tmp_path: Path) -> None:
        daily = _MODULE.cache_path_for(tmp_path, "BTC-USD", "1d")
        hourly = _MODULE.cache_path_for(tmp_path, "BTC-USD", "1h")
        assert daily != hourly
        assert daily.parent == tmp_path
        assert hourly.parent.name == "1h"
