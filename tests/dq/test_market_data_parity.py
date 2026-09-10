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
- Manifest dataset ids are Task 5's real backfill keys (normalized ticker via
  ``normalize_ticker``; macro ``fred__{SERIES}`` lowercase) — verified against
  ``scripts/backfill_market_data_r2.py::R2StoreAdapter.put_generation``.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import digiquant.mcp_server as mcp
import polars as pl
import pytest

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
    from digiquant.data.prices.technicals import compute_indicators

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
    from digiquant.data.prices.r2_history import macro_latest_pointer_key

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
    from datetime import date as _date
    from datetime import timedelta as _td

    from digiquant.data.prices.fetchers import FetchResult

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
    as_of = (_date.fromisoformat(seal) + _td(days=30)).isoformat()
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
    assert live["stale"] is True
    assert [str(r["date"]) for r in live["rows"]] == dates


def test_r2_per_ticker_error_entry_serves_history_only_and_marks_stale(monkeypatch):
    """Fail-soft serving + loud flag: a vendor error-entry never blanks the run."""
    from datetime import date as _date
    from datetime import timedelta as _td

    from digiquant.data.prices.fetchers import FetchResult

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
    as_of = (_date.fromisoformat(seal) + _td(days=1)).isoformat()
    live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
    assert [str(r["date"]) for r in live["rows"]] == dates
    assert [r["close"] for r in live["rows"]] == pytest.approx(closes)
    assert live["stale"] is True
