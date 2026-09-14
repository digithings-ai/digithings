"""R2-vs-Supabase-golden parity for the market-data cutover (#3780, Task 7).

Compares the flagged R2 backend (``DIGIQUANT_MARKET_DATA_BACKEND=r2``) against
the Task 1 pre-cutover goldens (``tests/fixtures/supabase-answers/*.json``)
through the UNMOCKED read path (fake R2 store serving real parquet bytes).

Adaptations vs the brief sketch, verified against the real fixtures:
- Golden technicals are ``{ticker, latest, window}`` newest-first dicts over
  TECHNICAL_COLUMNS with NO ``close`` column — so the date assertion runs
  against ``golden["technicals"]["SPY"]["window"]`` (ascending), and the
  sketch's ``< 1e-12`` close assertion is replaced by a close round-trip
  through the serving path (goldens carry no close to compare against).
- R2 technicals rows are wide dicts (OHLCV + ``compute_indicators`` output);
  value parity pins the golden-column subset plus an exact round-trip vs
  ``compute_indicators`` on the same history.
- Macro IS exact value parity: the R2 macro path does no recomputation, so
  golden DGS10/VIXCLS values embedded in synthetic parquet come back as-is.
- Close coverage is SYNTHETIC wiring-only (#3780 Task 7 fix round I2): the
  Task 1 goldens carry no ``close`` column anywhere (indicator-only windows),
  so ``100.0+i*0.5`` closes embedded in the fake parquet only prove the serving
  path round-trips values — NOT that R2 values equal Supabase values. True
  value parity is owned by the Task 10 contract tests (see premise guard below).
- Manifest dataset ids are Task 5's real backfill keys (normalized ticker via
  ``normalize_ticker``; macro ``fred__{SERIES}`` lowercase) — verified against
  ``scripts/backfill_market_data_r2.py::R2StoreAdapter.put_generation``.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
from datetime import date as _dt_date
from datetime import timedelta as _tdelta_mod
from pathlib import Path

import digiquant.mcp_server as mcp
import polars as pl
import pytest
from digiquant.dashboard.performance_returns import calculate_performance_returns
from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.data.prices.fetchers import FetchResult
from digiquant.data.prices.r2_history import macro_latest_pointer_key
from digiquant.data.prices.technicals import compute_indicators
from digiquant.portfolio.candidates import select_focus_tickers
from digiquant.portfolio.h9_cost_evidence import _fetch_price_row, _load_symbol_history
from digiquant.portfolio.phases.phase7e_risk_sizing import _load_ticker_risk
from digiquant.portfolio.portfolio_materialize import _upsert_portfolio_metrics
from digiquant.portfolio.writers.commit_io import _interval_price_returns
from digiquant.portfolio.writers.ledger_io import _last_closes
from digiquant.portfolio.writers.opening_snapshot import _price_for_symbol
from digiquant.research.data import queries as q
from digiquant.research.data.queries import TECHNICAL_COLUMNS
from digiquant.research.data.tools import build_data_tool_dispatcher
from digiquant.research.forecast_outcomes import _fetch_session_close
from digiquant.research.supabase_io import (
    query_macro_series_freshness,
    query_price_deltas,
    query_price_technicals_freshness,
    query_returns_window,
)

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

_GOLDENS = Path("tests/fixtures/supabase-answers")
_DATES = ("2024-12-31", "2025-03-15", "2025-08-29")


@pytest.fixture(autouse=True)
def _clear_ttl():
    ttl = getattr(mcp, "_ttl", None)
    if ttl is not None:
        ttl.clear()
    yield
    if ttl is not None:
        ttl.clear()


def _load_golden(date: str) -> dict:
    return json.loads((_GOLDENS / f"{date}.json").read_text())


def _price_payload(dates: list[str], closes: list[float]) -> tuple[bytes, str]:
    frame = pl.DataFrame(
        {
            "date": dates,
            "ticker": ["SPY"] * len(dates),
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(dates),
        }
    )
    buf = io.BytesIO()
    frame.write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _macro_payload(rows: list[dict]) -> tuple[bytes, str]:
    buf = io.BytesIO()
    pl.DataFrame(rows).write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


class _FakeR2Store:
    """Minimal R2HistoryStore double: pointer -> (generation bytes, sha)."""

    def __init__(self, pointer_map: dict[str, tuple[bytes, str]]) -> None:
        self._pointer_map = pointer_map

    def get_generation(self, key: str, sha256: str) -> bytes:
        for _pointer, (payload, sha) in self._pointer_map.items():
            if sha == sha256:
                return payload
        raise KeyError(key)

    def read_latest(self, pointer_key: str) -> str:
        if pointer_key not in self._pointer_map:
            raise KeyError(pointer_key)
        return pointer_key


def _r2_env(monkeypatch: pytest.MonkeyPatch, store: _FakeR2Store, manifest: dict) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: manifest)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: store)


def _spy_history_for_golden(golden: dict) -> tuple[list[str], list[float]]:
    """Synthetic SPY history on the golden window's dates (ascending)."""
    dates = sorted(r["date"] for r in golden["technicals"]["SPY"]["window"])
    closes = [100.0 + i * 0.5 for i in range(len(dates))]
    return dates, closes


def test_golden_fixtures_carry_no_close_column_so_close_parity_is_wiring_only():
    """I2 premise guard: closes here are synthetic BY NECESSITY, not by choice.

    If a future golden gains a ``close`` column, this test fails — upgrade the
    close round-trip to real golden-value parity then (Task 10 contract tests
    own value parity until that happens).
    """
    for date in _DATES:
        golden = _load_golden(date)
        for ticker, tech in golden["technicals"].items():
            assert all("close" not in row for row in tech["window"]), (date, ticker)
            assert "close" not in tech["latest"], (date, ticker)


def test_r2_backend_matches_supabase_goldens(monkeypatch):
    """Parity: R2-served rows align to each golden's dates; closes round-trip."""
    for date in _DATES:
        golden = _load_golden(date)
        dates, closes = _spy_history_for_golden(golden)
        payload, sha = _price_payload(dates, closes)
        seal = dates[-1]
        manifest = {
            "version": 1,
            "as_of": seal,
            "datasets": {
                "SPY": {
                    "object": f"market-data/price/SPY/{seal}.parquet",
                    "sha256": sha,
                    "rows": len(dates),
                    "as_of": seal,
                }
            },
        }
        _r2_env(
            monkeypatch,
            _FakeR2Store({f"market-data/price/SPY/{seal}.parquet": (payload, sha)}),
            manifest,
        )
        # NOTE: _FakeR2Store.get_generation matches on sha; the manifest entry
        # object key above is what a real Task 5 backfill writes.
        live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=seal))
        assert live["as_of"] == seal
        assert live["stale"] is False
        assert [str(r["date"]) for r in live["rows"]] == dates
        assert [r["close"] for r in live["rows"]] == pytest.approx(closes)
        # Golden-column subset: every Supabase technicals column is served.
        golden_cols = [c for c in golden["technicals"]["SPY"]["window"][0] if c != "date"]
        for col in golden_cols:
            assert col in live["rows"][0], f"R2 rows missing golden column {col!r}"


def test_r2_technicals_values_match_compute_indicators(monkeypatch):
    """Value parity: served indicators == compute_indicators on the same history."""
    golden = _load_golden("2025-08-29")
    dates, closes = _spy_history_for_golden(golden)
    payload, sha = _price_payload(dates, closes)
    seal = dates[-1]
    manifest = {
        "version": 1,
        "as_of": seal,
        "datasets": {"SPY": {"object": "gen", "sha256": sha, "rows": len(dates), "as_of": seal}},
    }
    _r2_env(monkeypatch, _FakeR2Store({"gen": (payload, sha)}), manifest)
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=seal))
    hist = pl.read_parquet(io.BytesIO(payload)).with_columns(pl.col("date").cast(pl.Date))
    expected = compute_indicators(hist.rename({"date": "timestamp"}))
    assert len(live["rows"]) == expected.height
    for got, want in zip(live["rows"], expected.to_dicts()):
        for col in ("sma_50", "rsi_14", "macd_hist"):
            assert got[col] == pytest.approx(want[col], nan_ok=True)


def test_r2_macro_matches_supabase_goldens_exactly(monkeypatch):
    """Macro value parity: golden observations embedded in parquet come back as-is."""
    golden = _load_golden("2025-08-29")
    pointer_map: dict[str, tuple[bytes, str]] = {}
    datasets: dict[str, dict] = {}
    for sid in golden["series_ids"]:
        rows = list(reversed(golden["macro"][sid]["window"]))
        payload, sha = _macro_payload(rows)
        pointer = macro_latest_pointer_key("fred", sid)
        pointer_map[pointer] = (payload, sha)
        datasets[f"fred__{sid}"] = {"object": pointer, "sha256": sha, "rows": len(rows)}
    latest_obs = max(
        r["obs_date"] for sid in golden["series_ids"] for r in golden["macro"][sid]["window"]
    )
    manifest = {"version": 1, "as_of": latest_obs, "datasets": datasets}
    _r2_env(monkeypatch, _FakeR2Store(pointer_map), manifest)
    live = json.loads(
        mcp.digiquant_get_macro_series(golden["series_ids"], lookback=6, as_of=latest_obs)
    )
    assert live["as_of"] == latest_obs
    assert live["stale"] is False
    for sid in golden["series_ids"]:
        assert live["series"][sid]["window"] == golden["macro"][sid]["window"][::-1]
        assert live["series"][sid]["latest"] == golden["macro"][sid]["latest"]


def test_r2_as_of_seals_rows_at_run_date(monkeypatch):
    """Cutover core: an earlier as_of serves a strict prefix (no look-ahead)."""
    golden = _load_golden("2025-08-29")
    dates, closes = _spy_history_for_golden(golden)
    payload, sha = _price_payload(dates, closes)
    seal = dates[-1]
    manifest = {
        "version": 1,
        "as_of": seal,
        "datasets": {"SPY": {"object": "gen", "sha256": sha, "rows": len(dates), "as_of": seal}},
    }
    _r2_env(monkeypatch, _FakeR2Store({"gen": (payload, sha)}), manifest)
    mid = dates[len(dates) // 2]
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=mid))
    assert [str(r["date"]) for r in live["rows"]] == [d for d in dates if d <= mid]


def test_r2_stale_manifest_marks_envelope_stale(monkeypatch):
    """Task 6 gate wired into the read path: seal >5 trading days behind as_of."""
    golden = _load_golden("2024-12-31")
    dates, closes = _spy_history_for_golden(golden)
    payload, sha = _price_payload(dates, closes)
    seal = dates[-1]
    manifest = {
        "version": 1,
        "as_of": seal,
        "datasets": {"SPY": {"object": "gen", "sha256": sha, "rows": len(dates), "as_of": seal}},
    }
    _r2_env(monkeypatch, _FakeR2Store({"gen": (payload, sha)}), manifest)
    monkeypatch.setattr(
        "digiquant.data.prices.fetchers.fetch_batch",
        lambda tickers, **kwargs: FetchResult(frames={}, errors={}),
    )
    # Seal +30d is stale on any weekday alignment; the live overlap is empty so
    # the served rows are exactly the sealed history, flagged stale.
    as_of = (_dt_date.fromisoformat(seal) + _tdelta_mod(days=30)).isoformat()
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
    assert live["stale"] is True
    assert [str(r["date"]) for r in live["rows"]] == dates


def test_r2_per_ticker_error_entry_serves_history_only_and_marks_stale(monkeypatch):
    """Fail-soft serving + loud flag: a vendor error-entry never blanks the run."""
    golden = _load_golden("2024-12-31")
    dates, closes = _spy_history_for_golden(golden)
    payload, sha = _price_payload(dates, closes)
    seal = dates[-1]
    manifest = {
        "version": 1,
        "as_of": seal,
        "datasets": {"SPY": {"object": "gen", "sha256": sha, "rows": len(dates), "as_of": seal}},
    }
    _r2_env(monkeypatch, _FakeR2Store({"gen": (payload, sha)}), manifest)
    monkeypatch.setattr(
        "digiquant.data.prices.fetchers.fetch_batch",
        lambda tickers, **kwargs: FetchResult(frames={}, errors={"SPY": "no_data"}),
    )
    # Seal +1d keeps the gate fresh on any weekday alignment, isolating the
    # error-entry flag: rows are history-only AND stale solely via the entry.
    as_of = (_dt_date.fromisoformat(seal) + _tdelta_mod(days=1)).isoformat()
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
    assert [str(r["date"]) for r in live["rows"]] == dates
    assert [r["close"] for r in live["rows"]] == pytest.approx(closes)
    assert live["stale"] is True


# ─── Task 7b: remaining bespoke readers → R2 seams ────────────────────────
#
# Each test drives one reader twice on as_of="2025-08-29": once against a
# seeded FakeSupabaseClient (supabase backend) and once against fake R2
# generations holding the SAME closes (r2 backend, exploding client proves no
# Supabase market-table read happens). Dates must match; recomputed indicator
# values within ±1e-9 (parquet float round-trip); stored closes/macro exact.
# FAILS while the reader is Supabase-only (exploding client raises).
#
# Nested value comparison uses ``pytest.approx(..., nan_ok=True)`` directly
# (strict on keys/length, exact on non-numerics) — no bespoke helper.

_T7B_AS_OF = "2025-08-29"
_T7B_RUN_DATE = _dt_date(2025, 8, 29)
_T7B_TICKERS = ("SPY", "QQQ")
_T7B_MACRO = ("DGS10", "VIXCLS")


class _ExplodingMarketClient:
    """Proves the R2 path never touches Supabase market tables."""

    def table(self, name: str):  # score:allow untyped def — test fake mirrors client surface
        raise AssertionError(f"Supabase market-table read after cutover: {name!r}")


def _t7b_dates(n: int = 80) -> list[str]:
    end = _dt_date.fromisoformat(_T7B_AS_OF)
    return [(end - _tdelta_mod(days=n - 1 - i)).isoformat() for i in range(n)]


def _t7b_closes(n: int = 80, base: float = 100.0) -> list[float]:
    return [round(base + i * 0.37 + (i % 7) * 0.11, 2) for i in range(n)]


def _t7b_price_payload(ticker: str, dates: list[str], closes: list[float]) -> tuple[bytes, str]:
    frame = pl.DataFrame(
        {
            "date": dates,
            "ticker": [ticker] * len(dates),
            "open": closes,
            "high": [c + 0.2 for c in closes],
            "low": [c - 0.2 for c in closes],
            "close": closes,
            "volume": [1_000_000 + i * 1000 for i in range(len(dates))],
        }
    )
    buf = io.BytesIO()
    frame.write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _t7b_indicator_rows(ticker: str, dates: list[str], closes: list[float]) -> list[dict]:
    """Supabase-shaped stored technicals with compute_indicators values."""
    payload, _ = _t7b_price_payload(ticker, dates, closes)
    hist = pl.read_parquet(io.BytesIO(payload)).with_columns(pl.col("date").cast(pl.Date))
    computed = compute_indicators(hist.rename({"date": "timestamp"})).to_dicts()
    rows = []
    for d, ind in zip(dates, computed):
        row: dict = {"ticker": ticker, "date": d}
        for col in (*TECHNICAL_COLUMNS, "hist_vol_21"):
            if col == "date":
                continue
            val = ind.get(col)
            row[col] = None if val is None else float(val)
        rows.append(row)
    return rows


def _t7b_hist_rows(ticker: str, dates: list[str], closes: list[float]) -> list[dict]:
    return [
        {
            "date": d,
            "ticker": ticker,
            "open": c,
            "high": c + 0.2,
            "low": c - 0.2,
            "close": c,
            "volume": 1_000_000 + i * 1000,
        }
        for i, (d, c) in enumerate(zip(dates, closes))
    ]


def _t7b_macro_rows() -> list[dict]:
    dates = _t7b_dates(8)
    rows = []
    for sid, base in (("DGS10", 4.2), ("VIXCLS", 18.5), ("VXVCLS", 22.1)):
        for i, d in enumerate(dates):
            rows.append(
                {
                    "source": "fred",
                    "series_id": sid,
                    "obs_date": d,
                    "value": round(base + i * 0.05, 3),
                    "unit": "percent" if sid == "DGS10" else "index",
                }
            )
    # FEDPROB prediction-market rows: Supabase-only by design (no R2
    # generation, mirroring prod) — the dispatcher fedprob pin reads these.
    fed_obs = "2025-08-28"
    rows.extend(
        [
            {
                "source": "kalshi",
                "series_id": "FEDPROB/2025-09-17/upper_gt_4",
                "obs_date": fed_obs,
                "value": 0.7,
                "meta": {},
            },
            {
                "source": "kalshi",
                "series_id": "FEDPROB/2025-09-17/upper_gt_4.25",
                "obs_date": fed_obs,
                "value": 0.3,
                "meta": {},
            },
            {
                "source": "polymarket",
                "series_id": "FEDPROB/2025-09-17/pm/will-the-fed-hold",
                "obs_date": fed_obs,
                "value": 0.65,
                "meta": {"question": "Will the Fed hold?"},
            },
        ]
    )
    return rows


def _t7b_supabase_client(
    dates: list[str], closes_by_ticker: dict[str, list[float]]
) -> FakeSupabaseClient:
    hist: list[dict] = []
    tech: list[dict] = []
    for ticker, closes in closes_by_ticker.items():
        hist.extend(_t7b_hist_rows(ticker, dates, closes))
        tech.extend(_t7b_indicator_rows(ticker, dates, closes))
    return FakeSupabaseClient(
        canned_reads={
            "price_history": hist,
            "price_technicals": tech,
            "macro_series_observations": _t7b_macro_rows(),
        }
    )


def _t7b_r2_env(
    monkeypatch: pytest.MonkeyPatch,
    dates: list[str],
    closes_by_ticker: dict[str, list[float]],
) -> None:
    pointer_map: dict[str, tuple[bytes, str]] = {}
    datasets: dict[str, dict] = {}
    for ticker, closes in closes_by_ticker.items():
        payload, sha = _t7b_price_payload(ticker, dates, closes)
        gen_key = f"market-data/price/{ticker}/{_T7B_AS_OF}.parquet"
        pointer_map[gen_key] = (payload, sha)
        datasets[ticker] = {
            "object": gen_key,
            "sha256": sha,
            "rows": len(dates),
            "as_of": _T7B_AS_OF,
        }
    # FRED-sourced series get R2 generations; FEDPROB rows deliberately do
    # not (Supabase-only by design — get_fed_rate_probabilities documents it).
    for sid in (*_T7B_MACRO, "VXVCLS"):
        rows = sorted(
            (r for r in _t7b_macro_rows() if r["series_id"] == sid),
            key=lambda r: r["obs_date"],
        )
        payload, sha = _macro_payload(rows)
        pointer = macro_latest_pointer_key("fred", sid)
        pointer_map[pointer] = (payload, sha)
        datasets[f"fred__{sid}"] = {"object": pointer, "sha256": sha, "rows": len(rows)}
    manifest = {"version": 1, "as_of": _T7B_AS_OF, "datasets": datasets}
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    _r2_env(monkeypatch, _FakeR2Store(pointer_map), manifest)


def _t7b_both(monkeypatch: pytest.MonkeyPatch):
    """(supabase_client, ) with R2 fakes armed; caller sets the backend per drive."""
    dates = _t7b_dates()
    closes = {t: _t7b_closes(base=100.0 if t == "SPY" else 200.0) for t in _T7B_TICKERS}
    sup = _t7b_supabase_client(dates, closes)
    _t7b_r2_env(monkeypatch, dates, closes)
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
    return dates, closes, sup


def _use_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")


def _use_r2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")


def test_get_price_technicals_helper_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = q.get_price_technicals(client=sup, ticker="SPY", lookback=20, as_of=_T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = q.get_price_technicals(
        client=_ExplodingMarketClient(), ticker="SPY", lookback=20, as_of=_T7B_RUN_DATE
    )
    assert [r["date"] for r in got["window"]] == [r["date"] for r in want["window"]]
    # The shared fake ignores select() projections, so project the Supabase
    # side through the helper's real TECHNICAL_COLUMNS select (production
    # PostgREST returns exactly these keys).
    want_window = [{k: r.get(k) for k in q.TECHNICAL_COLUMNS} for r in want["window"]]
    assert got["window"] == pytest.approx(want_window, nan_ok=True)
    assert got["latest"] == pytest.approx(
        {k: want["latest"].get(k) for k in q.TECHNICAL_COLUMNS}, nan_ok=True
    )


def test_get_macro_series_helper_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = q.get_macro_series(
        client=sup, series_ids=list(_T7B_MACRO), lookback=6, as_of=_T7B_RUN_DATE
    )
    _use_r2(monkeypatch)
    got = q.get_macro_series(
        client=_ExplodingMarketClient(),
        series_ids=list(_T7B_MACRO),
        lookback=6,
        as_of=_T7B_RUN_DATE,
    )
    # Same select-projection note as the technicals test: the helper's real
    # select is series_id,obs_date,value,unit (the fake returns whole rows).
    cols = ("series_id", "obs_date", "value", "unit")
    want_proj = {
        sid: {
            "latest": {k: payload["latest"].get(k) for k in cols} if payload["latest"] else {},
            "window": [{k: r.get(k) for k in cols} for r in payload["window"]],
        }
        for sid, payload in want.items()
    }
    # pytest.approx handles one dict level: compare latest + window per series.
    assert set(got) == set(want_proj)
    for sid, payload in want_proj.items():
        assert got[sid]["latest"] == pytest.approx(payload["latest"], nan_ok=True)
        assert got[sid]["window"] == pytest.approx(payload["window"], nan_ok=True)


def test_get_market_context_r2_matches_supabase(monkeypatch):
    # Pattern from the thin-wrapper parity tests, applied to the bulk reader:
    # same as_of on both backends, identical dates, values within ±1e-9.
    # FAILS while the reader is Supabase-only (no R2 path to drive).
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {
        "tickers": list(_T7B_TICKERS),
        "series_ids": list(_T7B_MACRO),
        "run_date": _T7B_RUN_DATE,
    }
    _use_supabase(monkeypatch)
    want = q.get_market_context(client=sup, **kwargs)
    _use_r2(monkeypatch)
    got = q.get_market_context(client=_ExplodingMarketClient(), **kwargs)
    assert got["as_of"] == want["as_of"] == _T7B_AS_OF
    assert sorted(got["price_technicals"]) == sorted(want["price_technicals"])
    for ticker, row in want["price_technicals"].items():
        assert got["price_technicals"][ticker] == pytest.approx(row, nan_ok=True)
    assert set(got["macro_series"]) == set(want["macro_series"])
    for sid, row in want["macro_series"].items():
        assert got["macro_series"][sid] == pytest.approx(row, nan_ok=True)


def test_get_market_breadth_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = q.get_market_breadth(client=sup, run_date=_T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = q.get_market_breadth(client=_ExplodingMarketClient(), run_date=_T7B_RUN_DATE)
    assert got == pytest.approx(want, nan_ok=True)


def test_sector_relative_strength_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"etfs": ["QQQ"], "benchmark": "SPY", "lookback_days": 70}
    _use_supabase(monkeypatch)
    want = q.get_sector_relative_strength(client=sup, run_date=_T7B_RUN_DATE, **kwargs)
    _use_r2(monkeypatch)
    got = q.get_sector_relative_strength(
        client=_ExplodingMarketClient(), run_date=_T7B_RUN_DATE, **kwargs
    )
    assert set(got) == set(want)
    for etf, row in want.items():
        assert got[etf] == pytest.approx(row, nan_ok=True)


def test_etf_flows_proxy_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"etfs": list(_T7B_TICKERS)}
    _use_supabase(monkeypatch)
    want = q.get_etf_flows_proxy(client=sup, run_date=_T7B_RUN_DATE, **kwargs)
    _use_r2(monkeypatch)
    got = q.get_etf_flows_proxy(client=_ExplodingMarketClient(), run_date=_T7B_RUN_DATE, **kwargs)
    assert got["as_of"] == want["as_of"] == _T7B_AS_OF
    assert got["note"] == want["note"]
    assert got["universe_size"] == want["universe_size"]
    assert set(got["flows"]) == set(want["flows"])
    for ticker, row in want["flows"].items():
        assert got["flows"][ticker] == pytest.approx(row, nan_ok=True)


def test_return_correlations_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"tickers": list(_T7B_TICKERS), "lookback_days": 70}
    _use_supabase(monkeypatch)
    want = q.get_return_correlations(client=sup, run_date=_T7B_RUN_DATE, **kwargs)
    _use_r2(monkeypatch)
    got = q.get_return_correlations(
        client=_ExplodingMarketClient(), run_date=_T7B_RUN_DATE, **kwargs
    )
    assert want is not None and got is not None
    assert got.sort(["a", "b"]).to_dicts() == pytest.approx(
        want.sort(["a", "b"]).to_dicts(), nan_ok=True
    )


def test_query_price_deltas_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = query_price_deltas(client=sup, tickers=tuple(_T7B_TICKERS), run_date=_T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = query_price_deltas(
        client=_ExplodingMarketClient(), tickers=tuple(_T7B_TICKERS), run_date=_T7B_RUN_DATE
    )
    assert got == pytest.approx(want)


def test_query_returns_window_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    start = _T7B_RUN_DATE - _tdelta_mod(days=30)
    _use_supabase(monkeypatch)
    want = query_returns_window(client=sup, ticker="SPY", start_date=start, holding_days=5)
    _use_r2(monkeypatch)
    got = query_returns_window(
        client=_ExplodingMarketClient(), ticker="SPY", start_date=start, holding_days=5
    )
    assert want is not None and got is not None
    assert got[0] == pytest.approx(want[0])
    assert (got[1], got[2]) == (want[1], want[2])


def test_interval_price_returns_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {
        "tickers": tuple(_T7B_TICKERS),
        "start_date": _T7B_RUN_DATE - _tdelta_mod(days=30),
        "run_date": _T7B_RUN_DATE,
    }
    _use_supabase(monkeypatch)
    want = _interval_price_returns(client=sup, **kwargs)
    _use_r2(monkeypatch)
    got = _interval_price_returns(client=_ExplodingMarketClient(), **kwargs)
    assert got == pytest.approx(want)


def test_last_closes_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = _last_closes(client=sup, tickers=set(_T7B_TICKERS), run_date=_T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = _last_closes(
        client=_ExplodingMarketClient(), tickers=set(_T7B_TICKERS), run_date=_T7B_RUN_DATE
    )
    assert got == want


def test_fetch_session_close_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    _use_supabase(monkeypatch)
    want = _fetch_session_close(client=sup, ticker="SPY", session=_T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = _fetch_session_close(client=_ExplodingMarketClient(), ticker="SPY", session=_T7B_RUN_DATE)
    assert want is not None and got == want


def test_price_for_symbol_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"symbol": "SPY", "book_date": _T7B_RUN_DATE, "entry_price": None}
    _use_supabase(monkeypatch)
    want = _price_for_symbol(client=sup, **kwargs)
    _use_r2(monkeypatch)
    got = _price_for_symbol(client=_ExplodingMarketClient(), **kwargs)
    assert want is not None and got == want


def test_select_focus_tickers_r2_matches_supabase(monkeypatch):
    dates, _, sup = _t7b_both(monkeypatch)
    watchlist = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"]
    _use_supabase(monkeypatch)
    want = select_focus_tickers(
        client=sup, watchlist=watchlist, run_date=_T7B_RUN_DATE, holdings=["SPY"]
    )
    _use_r2(monkeypatch)
    got = select_focus_tickers(
        client=_ExplodingMarketClient(),
        watchlist=watchlist,
        run_date=_T7B_RUN_DATE,
        holdings=["SPY"],
    )
    assert got == want


def test_load_ticker_risk_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    tickers = list(_T7B_TICKERS)
    _use_supabase(monkeypatch)
    want = _load_ticker_risk(sup, tickers, _T7B_RUN_DATE)
    _use_r2(monkeypatch)
    got = _load_ticker_risk(_ExplodingMarketClient(), tickers, _T7B_RUN_DATE)  # type: ignore[arg-type]
    assert sorted(got) == sorted(want)
    for ticker in tickers:
        assert got[ticker].hist_vol_21 == pytest.approx(want[ticker].hist_vol_21, nan_ok=True)
        assert got[ticker].atr_pct == pytest.approx(want[ticker].atr_pct, nan_ok=True)


def test_freshness_probes_read_manifest_seal(monkeypatch):
    _, _, _ = _t7b_both(monkeypatch)
    _use_r2(monkeypatch)
    latest, count = query_price_technicals_freshness(client=_ExplodingMarketClient())  # type: ignore[arg-type]
    assert latest == _T7B_RUN_DATE
    assert count == len(_T7B_TICKERS)
    assert (
        query_macro_series_freshness(client=_ExplodingMarketClient())  # type: ignore[arg-type]
        == _T7B_RUN_DATE
    )


def test_portfolio_materialize_benchmark_r2_matches_supabase(monkeypatch):
    """Alpha tracks the R2 SPY closes under r2, the Supabase closes otherwise."""
    dates = _t7b_dates(25)
    nav_rows = [
        {
            "workspace_id": str(house_workspace_id()),
            "date": d,
            "nav": round(100.0 + i * 0.4, 2),
        }
        for i, d in enumerate(dates)
    ]
    # Supabase SPY: flat (benchmark return 0). R2 SPY: trending (return > 0).
    flat = [100.0] * len(dates)
    trend = [round(100.0 + i * 0.5, 2) for i in range(len(dates))]
    r2_dates, r2_closes = dates, {"SPY": trend}
    _t7b_r2_env(monkeypatch, r2_dates, r2_closes)
    sup_flat = _t7b_supabase_client(dates, {"SPY": flat})
    sup_flat.canned_reads["nav_history"] = nav_rows

    _use_supabase(monkeypatch)
    _upsert_portfolio_metrics(client=sup_flat, run_date=_T7B_RUN_DATE)
    sup_row = sup_flat.store["portfolio_metrics"][-1]

    r2_client = FakeSupabaseClient(canned_reads={"nav_history": nav_rows})
    _use_r2(monkeypatch)
    _upsert_portfolio_metrics(client=r2_client, run_date=_T7B_RUN_DATE)
    r2_row = r2_client.store["portfolio_metrics"][-1]

    navs = [r["nav"] for r in nav_rows]
    expect_sup = calculate_performance_returns(
        nav_values=navs, benchmark_closes=flat, benchmark_ticker="SPY"
    )
    expect_r2 = calculate_performance_returns(
        nav_values=navs, benchmark_closes=trend, benchmark_ticker="SPY"
    )
    assert sup_row["benchmark_return_pct"] == pytest.approx(expect_sup.benchmark_return_pct)
    assert r2_row["benchmark_return_pct"] == pytest.approx(expect_r2.benchmark_return_pct)
    assert r2_row["benchmark_return_pct"] != pytest.approx(sup_row["benchmark_return_pct"])


def test_h9_symbol_history_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"symbol": "SPY", "as_of_session": _T7B_AS_OF, "lookback_days": 20}
    _use_supabase(monkeypatch)
    want = _load_symbol_history(client=sup, **kwargs)
    _use_r2(monkeypatch)
    got = _load_symbol_history(client=_ExplodingMarketClient(), **kwargs)  # type: ignore[arg-type]
    assert got.height == want.height
    assert got.sort("date").to_dicts() == pytest.approx(want.sort("date").to_dicts(), nan_ok=True)


def test_h9_price_row_r2_matches_supabase(monkeypatch):
    _, _, sup = _t7b_both(monkeypatch)
    kwargs: dict = {"symbol": "SPY", "session_date": _T7B_AS_OF}
    _use_supabase(monkeypatch)
    want = _fetch_price_row(client=sup, **kwargs)
    _use_r2(monkeypatch)
    got = _fetch_price_row(client=_ExplodingMarketClient(), **kwargs)  # type: ignore[arg-type]
    assert want is not None and got is not None
    assert got == pytest.approx(want, nan_ok=True)


def test_dispatcher_matrix_rides_r2_backend(monkeypatch):
    """Dispatcher re-verify (second cutover): every data tool serves R2 data.

    Drives all six data tools through ``build_data_tool_dispatcher`` and
    diffs each against the direct-helper output. The five R2-backed tools run
    under r2 with an exploding client (any Supabase market-table read fails
    the test); ``get_fed_rate_probabilities`` is the documented Supabase
    exception (prediction-market odds have no R2 generation) — it runs with
    the seeded client and additionally pins that an exploding client
    surfaces an ``Error:`` instead of data. All six share the same
    run_date-as-as_of threading, pinned per tool below.
    """
    # Wide universe + long window: the dispatcher forwards no per-tool args,
    # so sector RS runs its default 220-day lookback over the default sector
    # ETFs and ETF flows its 63-day window — both need real fixture depth.
    dates = _t7b_dates(n=230)
    tickers = sorted(set(_T7B_TICKERS) | set(q.default_sector_etfs()))
    closes = {t: _t7b_closes(n=230, base=100.0 + 10.0 * i) for i, t in enumerate(tickers)}
    sup = _t7b_supabase_client(dates, closes)
    _t7b_r2_env(monkeypatch, dates, closes)
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
    _use_r2(monkeypatch)
    exploding = _ExplodingMarketClient()
    dispatch = build_data_tool_dispatcher(
        exploding,
        run_date=_T7B_RUN_DATE,  # type: ignore[arg-type]
    )

    def _drive(name: str, args: dict, direct) -> dict:
        # Exact identity: the dispatcher only routes + JSON-serializes the
        # direct-helper computation (lossless for these finite payloads), so
        # == pins the run_date-as-as_of threading with zero tolerance slack.
        out = json.loads(dispatch(name, args))
        assert out == direct
        return out

    macro_out = _drive(
        "get_macro_series",
        {"series_ids": list(_T7B_MACRO), "lookback": 6},
        q.get_macro_series(
            client=exploding,  # type: ignore[arg-type]
            series_ids=list(_T7B_MACRO),
            lookback=6,
            as_of=_T7B_RUN_DATE,
        ),
    )
    assert set(macro_out) == set(_T7B_MACRO)
    breadth_out = _drive(
        "get_market_breadth",
        {},
        q.get_market_breadth(client=exploding, run_date=_T7B_RUN_DATE),  # type: ignore[arg-type]
    )
    assert breadth_out["universe_size"] == len(tickers)
    sector_out = _drive(
        "get_sector_relative_strength",
        {},
        q.get_sector_relative_strength(client=exploding, run_date=_T7B_RUN_DATE),  # type: ignore[arg-type]
    )
    assert sector_out, "sector RS over 230d of closes must be non-trivial"
    vix_out = _drive(
        "get_vix_term_structure",
        {},
        q.get_vix_term_structure(client=exploding, run_date=_T7B_RUN_DATE),  # type: ignore[arg-type]
    )
    assert vix_out["state"] in {"contango", "backwardation"}
    flows_out = _drive(
        "get_etf_flows_proxy",
        {},
        q.get_etf_flows_proxy(client=exploding, run_date=_T7B_RUN_DATE),  # type: ignore[arg-type]
    )
    assert flows_out["universe_size"] > 0

    # Documented exception: fedprob stays Supabase-backed on both backends.
    fed_dispatch = build_data_tool_dispatcher(sup, run_date=_T7B_RUN_DATE)  # type: ignore[arg-type]
    fed_out = json.loads(fed_dispatch("get_fed_rate_probabilities", {}))
    fed_direct = q.get_fed_rate_probabilities(client=sup, run_date=_T7B_RUN_DATE)
    assert fed_out == fed_direct
    assert fed_out["sources"], "seeded FEDPROB rows must produce a real distribution"
    assert dispatch("get_fed_rate_probabilities", {}).startswith("Error:")


def test_r2_generation_window_shared_seam(monkeypatch):
    """Shared `_r2_generation_window` seam behind both R2 row helpers (#3780 fix round).

    The columns param selects the projection: strict for closes, lenient for
    OHLCV (generations missing a column omit it per row).
    """
    _, _, _ = _t7b_both(monkeypatch)
    _use_r2(monkeypatch)
    kwargs: dict = {"tickers": list(_T7B_TICKERS), "since": _t7b_dates()[0], "until": _T7B_AS_OF}
    assert q._r2_generation_window(
        **kwargs, columns=("date", "ticker", "close")
    ) == q.r2_close_rows(**kwargs)
    ohlcv = q._r2_generation_window(
        **kwargs,
        columns=("date", "ticker", "open", "high", "low", "close", "volume"),
        strict=False,
    )
    assert ohlcv == q.r2_ohlcv_rows(**kwargs)
    assert all(isinstance(r["date"], str) for r in ohlcv)
    assert all("volume" in r for r in ohlcv)


def test_r2_generation_window_retries_transient_faults(monkeypatch):
    """Central retry (#3780 fix round): a transient R2 fault retries, then succeeds."""
    dates, _, _ = _t7b_both(monkeypatch)
    _use_r2(monkeypatch)
    calls = {"n": 0}
    real_store = mcp._get_r2_store()

    class _FlakyStore:
        def get_generation(self, key, sha256):  # score:allow untyped def — test double
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("simulated disconnect")
            return real_store.get_generation(key, sha256)

        def read_latest(self, pointer_key):  # score:allow untyped def — test double
            return real_store.read_latest(pointer_key)

    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FlakyStore())
    monkeypatch.setattr(time, "sleep", lambda *_args: None)
    rows = q.r2_close_rows(tickers=["SPY"], since=dates[0], until=_T7B_AS_OF)
    assert calls["n"] == 2
    assert len(rows) == len(dates)


def test_r2_generation_window_unknown_ticker_fails_loud(monkeypatch):
    """Fail-loud errors never retry: unknown tickers raise on first attempt."""
    _, _, _ = _t7b_both(monkeypatch)
    _use_r2(monkeypatch)
    with pytest.raises(LookupError):
        q.r2_close_rows(tickers=["NOPE"], since=_t7b_dates()[0], until=_T7B_AS_OF)


def test_r2_generation_window_boto_client_error_pointer_miss_fails_loud(monkeypatch):
    """The real R2 backend's ClientError pointer miss → LookupError, not a raw boto error (#3951)."""

    class _BotoClientError(Exception):
        def __init__(self) -> None:
            super().__init__("An error occurred (NoSuchKey) when calling the GetObject operation")
            self.response = {
                "Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."},
                "ResponseMetadata": {"HTTPStatusCode": 404},
            }

    class _NoPointerStore:
        def get_generation(self, key, sha256):
            raise KeyError(key)

        def read_latest(self, pointer_key):
            raise _BotoClientError()

    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(
        mcp, "_read_manifest", lambda: {"version": 1, "as_of": _T7B_AS_OF, "datasets": {}}
    )
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _NoPointerStore())
    with pytest.raises(LookupError, match="unknown ticker"):
        q.r2_close_rows(tickers=["NOPE"], since=_t7b_dates()[0], until=_T7B_AS_OF)
