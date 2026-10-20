"""Unit tests for digiquant.data.prices.supabase_writer (fake Supabase client)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import polars as pl
import pytest
from digiquant.dashboard.instrument_metadata import InstrumentMetadata
from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices.supabase_writer import (
    ohlcv_to_price_history_rows,
    technicals_to_rows,
    upsert_fx_intraday_observations,
    upsert_instruments,
    upsert_macro_observations,
    upsert_price_history,
    upsert_price_technicals,
)

# ─── Fake Supabase (ports the research pattern) ───────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    table_name: str
    store: dict[str, list[dict[str, Any]]]
    _upsert: list[dict[str, Any]] | None = None
    _on_conflict: str | None = None
    _returning: Any = None

    def upsert(
        self,
        rows: list[dict[str, Any]],
        on_conflict: str | None = None,
        *,
        returning: Any = None,
    ) -> "_FakeQuery":
        self._upsert = list(rows)
        self._on_conflict = on_conflict
        self._returning = returning
        return self

    def execute(self) -> _FakeResponse:
        if self._upsert is not None:
            self.store.setdefault(self.table_name, []).extend(self._upsert)
            if _is_minimal(self._returning):
                # PostgREST honours Prefer: return=minimal with a 201 and an
                # empty body — the rows are written, nothing is echoed back.
                return _FakeResponse(data=[])
            return _FakeResponse(data=self._upsert)
        return _FakeResponse(data=[])


def _is_minimal(returning: Any) -> bool:
    """True when ``returning`` asks PostgREST for no representation body."""
    return getattr(returning, "value", returning) == "minimal"


@dataclass
class _RecordingQuery(_FakeQuery):
    """A fake that records the ``returning`` argument of every chunk."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def upsert(
        self,
        rows: list[dict[str, Any]],
        on_conflict: str | None = None,
        *,
        returning: Any = None,
    ) -> "_RecordingQuery":
        self.calls.append(
            {
                "table": self.table_name,
                "rows": len(rows),
                "on_conflict": on_conflict,
                "returning": returning,
            }
        )
        return super().upsert(rows, on_conflict=on_conflict, returning=returning)


@dataclass
class _RecordingClient:
    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def table(self, name: str) -> _RecordingQuery:
        return _RecordingQuery(table_name=name, store=self.store, calls=self.calls)


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
def test_ohlcv_to_price_history_rows_produces_research_schema() -> None:
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


@pytest.mark.unit
def test_technicals_to_rows_omits_null_indicators_rather_than_nulling_them() -> None:
    """Regression for #1752.

    A daily run fetches only a trailing window, so long-window indicators are
    None during warmup while short-window ones are computed. Emitting the None
    as an explicit NULL upserts over the stored value and erased ~11 months of
    sma_200/sma_50/zscore_200 across all 252 tickers. The key must be OMITTED.
    """
    warm, cold = TECHNICAL_COLUMNS[0], TECHNICAL_COLUMNS[1]
    ind = pl.DataFrame({warm: [1.5], cold: [None]})
    ts = pl.Series("timestamp", [date(2025, 1, 1)])

    rows = technicals_to_rows(ind, "SPY", ts)

    assert len(rows) == 1
    row = rows[0]
    assert row[warm] == 1.5
    # The load-bearing assertion: absent, not present-and-None.
    assert cold not in row
    assert row["date"] == "2025-01-01" and row["ticker"] == "SPY"


@pytest.mark.unit
def test_upsert_price_technicals_groups_rows_by_key_set() -> None:
    """Regression for #1752.

    Because technicals_to_rows now omits None indicator keys, one batch can hold
    rows with differing key sets. PostgREST derives the bulk-upsert column list
    from the payload and rejects heterogeneous objects (PGRST102), so every
    outgoing batch must be internally homogeneous.
    """
    batches: list[list[dict[str, Any]]] = []

    class _RecordingQuery(_FakeQuery):
        def execute(self) -> _FakeResponse:
            if self._upsert is not None:
                batches.append(list(self._upsert))
            return super().execute()

    class _RecordingClient(FakeSupabaseClient):
        def table(self, name: str) -> _FakeQuery:
            return _RecordingQuery(table_name=name, store=self.store)

    a, b = TECHNICAL_COLUMNS[0], TECHNICAL_COLUMNS[1]
    rows = [
        {"date": "2025-01-01", "ticker": "SPY", a: 1.0, b: 2.0},
        {"date": "2025-01-02", "ticker": "SPY", a: 1.0},
        {"date": "2025-01-03", "ticker": "SPY", a: 1.0, b: 2.0},
    ]

    res = upsert_price_technicals(_RecordingClient(), rows)

    assert res.rows == 3
    assert len(batches) == 2, "rows with differing key sets must not share a batch"
    for batch in batches:
        keysets = {tuple(sorted(r)) for r in batch}
        assert len(keysets) == 1, f"heterogeneous batch would 400 on PostgREST: {keysets}"
    # Every input row still reaches the table exactly once.
    assert sum(len(b) for b in batches) == 3


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
        def upsert(self, rows, on_conflict=None, *, returning=None):
            captured["on_conflict"] = on_conflict
            return super().upsert(rows, on_conflict=on_conflict, returning=returning)

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
        def upsert(self, rows, on_conflict=None, *, returning=None):
            captured["on_conflict"] = on_conflict
            return super().upsert(rows, on_conflict=on_conflict, returning=returning)

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
def test_upsert_fx_intraday_observations_uses_interval_ts_conflict_key() -> None:
    """Intraday candles upsert on (source, series_id, interval, ts).

    ``interval`` is load-bearing: 5m and 1h bars share :00 opens, so without it
    in the key the 5m upsert would replace the 1h row.
    """
    captured: dict[str, Any] = {}

    class _CaptureQuery(_FakeQuery):
        def upsert(self, rows, on_conflict=None, *, returning=None):
            captured["on_conflict"] = on_conflict
            return super().upsert(rows, on_conflict=on_conflict, returning=returning)

    class _CaptureClient:
        def __init__(self):
            self.store: dict[str, list] = {}

        def table(self, name):
            captured["table"] = name
            return _CaptureQuery(table_name=name, store=self.store)

    client = _CaptureClient()
    rows = [
        {
            "source": "yahoo",
            "series_id": "FX/EUR",
            "interval": "1h",
            "ts": "2025-04-01T13:00:00+00:00",
            "open": 1.08,
            "high": 1.10,
            "low": 1.07,
            "close": 1.09,
        }
    ]
    res = upsert_fx_intraday_observations(client, rows)

    assert res.rows == 1
    assert res.table == "fx_intraday_observations"
    assert captured["table"] == "fx_intraday_observations"
    assert captured["on_conflict"] == "source,series_id,interval,ts"


@pytest.mark.unit
def test_upsert_fx_intraday_5m_and_1h_coexist_at_same_ts() -> None:
    """A fake with PostgREST on-conflict semantics: both bars survive one ts.

    Mirrors the new PK (source, series_id, interval, ts) in SQL: upserting a 5m
    candle at a :00 open must not overwrite the 1h candle at the same instant,
    while a re-served settled 5m candle still replaces its own previous row.
    """

    class _ConflictKeyedQuery:
        def __init__(self, client: "_ConflictKeyedClient") -> None:
            self._client = client
            self._rows: list[dict[str, Any]] = []
            self._on_conflict: str | None = None

        def upsert(self, rows, on_conflict=None, *, returning=None):
            self._rows = list(rows)
            self._on_conflict = on_conflict
            return self

        def execute(self) -> _FakeResponse:
            keys = (self._on_conflict or "").split(",")
            for row in self._rows:
                self._client.rows[tuple(row[k] for k in keys)] = row
            return _FakeResponse(data=self._rows)

    class _ConflictKeyedClient:
        def __init__(self) -> None:
            self.rows: dict[tuple[str, ...], dict[str, Any]] = {}

        def table(self, name: str) -> _ConflictKeyedQuery:
            return _ConflictKeyedQuery(self)

    client = _ConflictKeyedClient()
    ts = "2025-04-01T13:00:00+00:00"
    hourly = {
        "source": "yahoo",
        "series_id": "FX/EUR",
        "interval": "1h",
        "ts": ts,
        "open": 1.08,
        "high": 1.10,
        "low": 1.07,
        "close": 1.09,
    }
    five_min = {**hourly, "interval": "5m", "close": 1.085}

    res = upsert_fx_intraday_observations(client, [hourly, five_min])

    assert res.rows == 2
    assert len(client.rows) == 2, "5m and 1h at the same ts must both persist"
    assert client.rows[("yahoo", "FX/EUR", "5m", ts)]["close"] == 1.085
    assert client.rows[("yahoo", "FX/EUR", "1h", ts)]["close"] == 1.09

    # The trailing 5m candle is re-served settled: it replaces its own row only.
    settled = {**five_min, "close": 1.087}
    upsert_fx_intraday_observations(client, [settled])

    assert len(client.rows) == 2
    assert client.rows[("yahoo", "FX/EUR", "5m", ts)]["close"] == 1.087
    assert client.rows[("yahoo", "FX/EUR", "1h", ts)]["close"] == 1.09


@pytest.mark.unit
def test_upsert_empty_rows_is_noop() -> None:
    client = FakeSupabaseClient()
    assert upsert_price_history(client, []).rows == 0
    assert upsert_price_technicals(client, []).rows == 0
    assert upsert_macro_observations(client, []).rows == 0
    assert upsert_fx_intraday_observations(client, []).rows == 0
    assert client.store == {}


@pytest.mark.unit
def test_upsert_price_technicals_round_trip() -> None:
    client = FakeSupabaseClient()
    rows = [{"date": "2025-01-01", "ticker": "SPY", **{c: 1.0 for c in TECHNICAL_COLUMNS}}]
    res = upsert_price_technicals(client, rows)
    assert res.rows == 1
    stored = client.store["price_technicals"][0]
    # Schema parity: research reader expects at minimum `date` + `ticker`.
    assert stored["date"] == "2025-01-01" and stored["ticker"] == "SPY"
    for col in TECHNICAL_COLUMNS:
        assert col in stored


# ─── write egress: no representation body (DIG-1835) ───────────────────────
#
# Supabase bills egress on the response bytes a write sends back. postgrest-py
# defaults `returning=ReturnMethod.representation`, so every chunk we POST is
# echoed back in full and the body is charged. None of the five writers read
# that body — they count their own input batch — so `returning="minimal"`
# removes the write egress without changing what lands in the table.
#
# On the 2026-10-06 measurement (DIG-1811) `fx_intraday_observations` took 4,901
# POST upserts/day at 500 rows/chunk: ~2.4M rows echoed back per day, against a
# 270,358-row table that the writer only ever reads for its own row count.


def _fx_rows(n: int) -> list[dict[str, Any]]:
    return [
        {
            "source": "yahoo",
            "series_id": f"FX/EUR{i}",
            "interval": "1h",
            "ts": f"2025-04-01T{i % 24:02d}:00:00+00:00",
            "open": 1.08,
            "high": 1.10,
            "low": 1.07,
            "close": 1.09,
        }
        for i in range(n)
    ]


@pytest.mark.unit
def test_upsert_fx_intraday_requests_no_representation_body() -> None:
    """The largest measured egress driver must not ask for the rows back."""
    client = _RecordingClient()

    upsert_fx_intraday_observations(client, _fx_rows(4), chunk=2)

    assert len(client.calls) == 2
    for call in client.calls:
        assert _is_minimal(call["returning"]), (
            "fx_intraday_observations POST must request return=minimal; "
            f"got returning={call['returning']!r}"
        )


@pytest.mark.unit
def test_upsert_fx_intraday_returns_input_row_count_not_response_rows() -> None:
    """The row count must come from the input batch, not the echoed body.

    This is the safety property that makes return=minimal safe: with the body
    suppressed the writer still reports exactly what it was handed.
    """
    client = _RecordingClient()
    rows = _fx_rows(7)

    res = upsert_fx_intraday_observations(client, rows, chunk=3)

    assert res.rows == 7
    assert res.table == "fx_intraday_observations"
    assert len(client.store["fx_intraday_observations"]) == 7


@pytest.mark.unit
def test_every_upsert_helper_requests_no_representation_body() -> None:
    """Guard the whole writer surface, not just the one measured path.

    A helper that omits `returning` keeps the postgrest-py default and bills
    egress on every chunk, so the property belongs on all five helpers.
    """
    instrument = InstrumentMetadata(
        ticker="XLE",
        official_name="Energy Select Sector SPDR Fund",
        instrument_type="ETF",
        asset_class="EQUITY",
        category="sector-energy",
        provider="yahoo",
        source_updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    technicals = [{"date": "2025-01-01", "ticker": "SPY", **{c: 1.0 for c in TECHNICAL_COLUMNS}}]
    macro = [{"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-01", "value": 4.1}]
    history = [{"date": "2025-01-01", "ticker": "SPY", "open": 1, "high": 1, "low": 1, "close": 1}]

    cases = {
        "upsert_price_history": (upsert_price_history, history),
        "upsert_instruments": (upsert_instruments, [instrument]),
        "upsert_price_technicals": (upsert_price_technicals, technicals),
        "upsert_macro_observations": (upsert_macro_observations, macro),
        "upsert_fx_intraday_observations": (upsert_fx_intraday_observations, _fx_rows(1)),
    }

    offenders = []
    for name, (fn, payload) in cases.items():
        client = _RecordingClient()
        fn(client, payload)
        assert client.calls, f"{name} issued no upsert at all — the guard would be vacuous"
        offenders += [f"{name}: {c['returning']!r}" for c in client.calls if not _is_minimal(c["returning"])]

    assert not offenders, "helpers still requesting a representation body: " + "; ".join(offenders)
