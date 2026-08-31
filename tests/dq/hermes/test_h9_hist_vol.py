"""H9 cost evidence reads hist_vol_21 from price_technicals (#3299)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.olympus.hermes.h9_cost_evidence import _fetch_price_row, _load_symbol_history

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SESSION = "2026-08-29"


def test_fetch_price_row_joins_hist_vol_from_technicals() -> None:
    client = FakeSupabaseClient(
        canned_reads={
            "price_history": [
                {
                    "date": _SESSION,
                    "ticker": "SPY",
                    "close": 640.0,
                    "high": 642.0,
                    "low": 638.0,
                    "volume": 80_000_000,
                }
            ],
            "price_technicals": [
                {
                    "date": _SESSION,
                    "ticker": "SPY",
                    "hist_vol_21": 12.5,
                    "atr_pct": 0.8,
                }
            ],
        }
    )
    row = _fetch_price_row(client=client, symbol="SPY", session_date=_SESSION)
    assert row is not None
    assert row["close"] == 640.0
    assert row["hist_vol_21"] == 12.5
    assert row["atr_pct"] == 0.8


def test_load_symbol_history_joins_technicals_on_date() -> None:
    client = FakeSupabaseClient(
        canned_reads={
            "price_history": [
                {
                    "date": "2026-08-28",
                    "ticker": "QQQ",
                    "close": 500.0,
                    "high": 502.0,
                    "low": 498.0,
                    "volume": 40_000_000,
                },
                {
                    "date": _SESSION,
                    "ticker": "QQQ",
                    "close": 505.0,
                    "high": 507.0,
                    "low": 503.0,
                    "volume": 41_000_000,
                },
            ],
            "price_technicals": [
                {"date": _SESSION, "ticker": "QQQ", "hist_vol_21": 18.0, "atr_pct": 1.1}
            ],
        }
    )
    frame = _load_symbol_history(
        client=client,
        symbol="QQQ",
        as_of_session=_SESSION,
        lookback_days=5,
    )
    assert not frame.is_empty()
    latest = frame.filter(frame["date"] == _SESSION)
    assert latest["hist_vol_21"][0] == 18.0
    assert latest["atr_pct"][0] == 1.1
    older = frame.filter(frame["date"] == "2026-08-28")
    assert older["hist_vol_21"][0] is None


def test_load_symbol_history_joins_when_date_types_differ() -> None:
    client = FakeSupabaseClient(
        canned_reads={
            "price_history": [
                {
                    "date": date(2026, 8, 29),
                    "ticker": "SPY",
                    "close": 640.0,
                    "high": 642.0,
                    "low": 638.0,
                    "volume": 80_000_000,
                }
            ],
            "price_technicals": [
                {
                    "date": "2026-08-29",
                    "ticker": "SPY",
                    "hist_vol_21": 12.5,
                    "atr_pct": 0.8,
                }
            ],
        }
    )
    frame = _load_symbol_history(
        client=client,
        symbol="SPY",
        as_of_session=_SESSION,
        lookback_days=5,
    )
    assert frame["hist_vol_21"][0] == 12.5
