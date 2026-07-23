"""Unit tests for digiquant.data.prices.supabase_writer (fake Supabase client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from datetime import datetime, timezone
from typing import Any

import polars as pl
import pytest

from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices.supabase_writer import (
    ohlcv_to_price_history_rows,
    technicals_to_rows,
    upsert_instruments,
    upsert_macro_observations,
    upsert_price_history,
    upsert_price_technicals,
)
from digiquant.olympus.instrument_metadata import InstrumentMetadata


# ─── Fake Supabase (ports the Atlas pattern) ───────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    table_name: str
    store: dict[str, list[dict[str, Any]]]
    _upsert: list[dict[str, Any]] | None = None
    _on_conflict: str | None = None

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str | None = None) -> "_FakeQuery":
        self._upsert = list(rows)
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResponse:
        if self._upsert is not None:
            self.store.setdefault(self.table_name, []).extend(self._upsert)
            return _FakeResponse(data=self._upsert)
        return _FakeResponse(data=[])


@dataclass
class FakeSupabaseClient:
    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(table_name=name, store=self.store)


# ─── Helpers ───────────────────────────────────────────────────────────


def _ohlcv_df(n: int = 5, symbol: str = "SPY") -> pl.DataFrame:
    dates = [date(2025, 4, 1) + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": dates,
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1_000_000.0 + i * 1_000 for i in range(n)],
            "symbol": [symbol] * n,
        }
    )


# ─── ohlcv_to_price_history_rows ──────────────────────────────────────


@pytest.mark.unit
def test_ohlcv_to_price_history_rows_produces_atlas_schema() -> None:
    df = _ohlcv_df(3)
    rows = ohlcv_to_price_history_rows(df, "SPY")
    assert len(rows) == 3
    for r in rows:
        assert set(r.keys()) == {"date", "ticker", "open", "high", "low", "close", "volume"}
        assert r["ticker"] == "SPY"
        assert len(r["date"]) == 10  # YYYY-MM-DD
    assert rows[0]["date"] == "2025-04-01"


@pytest.mark.unit
def test_ohlcv_to_price_history_rows_volume_is_int() -> None:
    # price_history.volume is bigint; postgrest rejects float payloads with 22P02.
    df = _ohlcv_df(2)
    rows = ohlcv_to_price_history_rows(df, "SPY")
    for r in rows:
        assert isinstance(r["volume"], int)
        assert not isinstance(r["volume"], bool)


@pytest.mark.unit
def test_ohlcv_to_price_history_rows_skips_null_close() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [date(2025, 1, 1)],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [None],
            "volume": [100.0],
            "symbol": ["X"],
        }
    )
    assert ohlcv_to_price_history_rows(df, "X") == []


# ─── technicals_to_rows ───────────────────────────────────────────────


@pytest.mark.unit
def test_technicals_to_rows_matches_schema() -> None:
    ind = pl.DataFrame({c: [1.0, 2.0] for c in TECHNICAL_COLUMNS})
    ts = pl.Series("timestamp", [date(2025, 1, 1), date(2025, 1, 2)])
    rows = technicals_to_rows(ind, "SPY", ts)
    assert len(rows) == 2
    for r in rows:
        for col in TECHNICAL_COLUMNS:
            assert col in r
        assert r["ticker"] == "SPY"
        assert r["date"].startswith("2025-01-")


@pytest.mark.unit
def test_technicals_to_rows_drops_all_null_rows() -> None:
    ind = pl.DataFrame({c: [None, 1.0] for c in TECHNICAL_COLUMNS})
    ts = pl.Series("timestamp", [date(2025, 1, 1), date(2025, 1, 2)])
    rows = technicals_to_rows(ind, "SPY", ts)
    assert len(rows) == 1
    assert rows[0]["date"] == "2025-01-02"


# ─── upsert_* ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_upsert_price_history_chunks_and_records() -> None:
    client = FakeSupabaseClient()
    rows = [
        {
            "date": f"2025-01-{i:02d}",
            "ticker": "SPY",
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
        }
        for i in range(1, 13)
    ]
    res = upsert_price_history(client, rows, chunk=5)
    assert res.rows == 12
    assert res.table == "price_history"
    assert len(client.store["price_history"]) == 12


@pytest.mark.unit
def test_upsert_instruments_uses_ticker_conflict_key() -> None:
    captured: dict[str, Any] = {}

    class _CaptureQuery(_FakeQuery):
        def upsert(self, rows, on_conflict=None):
            captured["on_conflict"] = on_conflict
            return super().upsert(rows, on_conflict=on_conflict)

    class _CaptureClient:
        def __init__(self):
            self.store: dict[str, list] = {}

        def table(self, name):
            return _CaptureQuery(table_name=name, store=self.store)

    instrument = InstrumentMetadata(
        ticker="XLE",
        official_name="Energy Select Sector SPDR Fund",
        instrument_type="ETF",
        asset_class="EQUITY",
        category="sector-energy",
        provider="yahoo",
        source_updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    client = _CaptureClient()

    result = upsert_instruments(client, [instrument])

    assert result.rows == 1
    assert captured["on_conflict"] == "ticker"
    assert client.store["instruments"][0]["official_name"] == "Energy Select Sector SPDR Fund"


@pytest.mark.unit
def test_upsert_macro_observations_uses_on_conflict() -> None:
    captured: dict[str, Any] = {}

    class _CaptureQuery(_FakeQuery):
        def upsert(self, rows, on_conflict=None):
            captured["on_conflict"] = on_conflict
            return super().upsert(rows, on_conflict=on_conflict)

    class _CaptureClient:
        def __init__(self):
            self.store: dict[str, list] = {}

        def table(self, name):
            return _CaptureQuery(table_name=name, store=self.store)

    client = _CaptureClient()
    rows = [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2025-01-01",
            "value": 4.1,
            "unit": "percent",
        }
    ]
    res = upsert_macro_observations(client, rows)
    assert res.rows == 1
    assert captured["on_conflict"] == "source,series_id,obs_date"


@pytest.mark.unit
def test_upsert_empty_rows_is_noop() -> None:
    client = FakeSupabaseClient()
    assert upsert_price_history(client, []).rows == 0
    assert upsert_price_technicals(client, []).rows == 0
    assert upsert_macro_observations(client, []).rows == 0
    assert client.store == {}


@pytest.mark.unit
def test_upsert_price_technicals_round_trip() -> None:
    client = FakeSupabaseClient()
    rows = [{"date": "2025-01-01", "ticker": "SPY", **{c: 1.0 for c in TECHNICAL_COLUMNS}}]
    res = upsert_price_technicals(client, rows)
    assert res.rows == 1
    stored = client.store["price_technicals"][0]
    # Schema parity: Atlas reader expects at minimum `date` + `ticker`.
    assert stored["date"] == "2025-01-01" and stored["ticker"] == "SPY"
    for col in TECHNICAL_COLUMNS:
        assert col in stored
