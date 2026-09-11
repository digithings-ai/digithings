"""as_of read contract for the R2 market-data cutover (#3780, Task 10).

The serving path must never emit a row newer than the requested ``as_of``
(no look-ahead), and an ``as_of`` before the first sealed bar serves an
empty window. Unit-safe: a fake R2 store serves real parquet bytes through
the UNMOCKED ``_read_r2_window`` + envelope (no network, no creds).

The brief's literal sketch (unmocked MCP calls) FAILS in CI with
``KeyError: 'rows'`` — the backend defaults to ``supabase`` there and the
CI env carries no Supabase creds. These tests pin the same contract
against the R2 seam directly.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date as _date
from datetime import timedelta as _td

import digiquant.mcp_server as mcp
import polars as pl
import pytest

pytestmark = pytest.mark.unit

_SEAL = "2025-08-29"
_START = _date(2024, 1, 2)
_AS_OFS = ("2024-06-30", "2024-12-31", "2025-03-15", "2025-06-30", "2025-08-29")


@pytest.fixture(autouse=True)
def _clear_ttl():
    ttl = getattr(mcp, "_ttl", None)
    if ttl is not None:
        ttl.clear()
    yield
    if ttl is not None:
        ttl.clear()


def _history_dates() -> list[str]:
    end = _date.fromisoformat(_SEAL)
    n = (end - _START).days + 1
    return [(_START + _td(days=i)).isoformat() for i in range(n)]


def _price_payload(dates: list[str], closes: list[float]) -> tuple[bytes, str]:
    frame = pl.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [1_000_000.0] * len(dates),
        }
    )
    buf = io.BytesIO()
    frame.write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


class _FakeR2Store:
    """Minimal R2HistoryStore double serving fixed parquet bytes.

    Keyed on ``(key, sha256)`` like the production lookup
    (``store.get_generation(entry["object"], entry["sha256"])``): a wrong
    key or sha raises ``KeyError`` instead of serving the bytes.
    """

    def __init__(self, generations: dict[tuple[str, str], bytes]) -> None:
        self._generations = generations

    def get_generation(self, key: str, sha256: str) -> bytes:
        return self._generations[(key, sha256)]

    def read_latest(self, pointer_key: str) -> str:
        raise KeyError(pointer_key)


@pytest.fixture()
def _r2_seal(monkeypatch: pytest.MonkeyPatch) -> None:
    dates = _history_dates()
    closes = [round(100.0 + i * 0.13, 2) for i in range(len(dates))]
    payload, sha = _price_payload(dates, closes)
    key = f"market-data/price/SPY/{_SEAL}.parquet"
    manifest = {
        "version": 1,
        "as_of": _SEAL,
        "datasets": {"SPY": {"object": key, "sha256": sha}},
    }
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: manifest)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store({(key, sha): payload}))


def test_no_row_newer_than_asof(_r2_seal: None) -> None:
    for as_of in _AS_OFS:
        out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
        assert out["rows"], f"sealed history covers {as_of}, window must not be vacuous"
        assert all(r["date"] <= as_of for r in out["rows"])


def test_asof_before_first_bar_returns_empty_rows(_r2_seal: None) -> None:
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2000-01-01"))
    assert out["rows"] == []


def test_h9_session_past_seal_serves_sealed_tail(_r2_seal: None) -> None:
    """H9 seal coverage (#3780 Task 10 live-fire item): H9 reads the run_date
    session bar but R2 seals through the manifest ``as_of``. A session past
    the seal fail-softs to the sealed tail — never an empty frame or error."""
    from digiquant.portfolio.h9_cost_evidence import _load_symbol_history

    session = (_date.fromisoformat(_SEAL) + _td(days=7)).isoformat()
    frame = _load_symbol_history(client=None, symbol="SPY", as_of_session=session, lookback_days=20)
    assert not frame.is_empty()
    assert str(frame["date"].max()) <= _SEAL
