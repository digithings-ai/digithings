"""commit ``_latest_values`` R2 branch — no Supabase market read (#4053 T5).

``commit_io._enrich_positions`` seeds ``entry_price`` from the latest close and
``atr_pct`` from the latest technicals row. Both tables are dropped in
migration 127, so under ``DIGIQUANT_MARKET_DATA_BACKEND=r2`` the helper must
serve them from the sealed R2 generations (the previous body read Supabase
even under the flag).
"""

from __future__ import annotations

from datetime import date

import digiquant.mcp_server as mcp
import pytest
from digiquant.portfolio.writers import commit_io
from digiquant.portfolio.writers.commit_io import _latest_values

pytestmark = pytest.mark.unit


def test_latest_close_uses_newest_r2_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(
        commit_io,
        "r2_close_rows",
        lambda **kwargs: [
            {"date": "2026-09-10", "ticker": "SPY", "close": 100.0},
            {"date": "2026-09-14", "ticker": "SPY", "close": 101.5},
            {"date": "2026-09-11", "ticker": "QQQ", "close": 55.0},
        ],
    )
    out = _latest_values(None, "price_history", "close", ["SPY", "QQQ"], date(2026, 9, 15))
    assert out == {"SPY": 101.5, "QQQ": 55.0}


def test_latest_values_is_fail_soft_on_r2_fault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")

    def _boom(**kwargs):
        raise LookupError("unknown ticker 'ZZZ'")

    monkeypatch.setattr(commit_io, "r2_close_rows", _boom)
    assert _latest_values(None, "price_history", "close", ["ZZZ"], date(2026, 9, 15)) == {}


def test_latest_technicals_reads_sealed_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(
        mcp,
        "_read_r2_window",
        lambda ticker, as_of, manifest=None: [
            {"date": "2026-09-10", "atr_pct": 1.0},
            {"date": "2026-09-14", "atr_pct": 2.5},
        ],
    )
    out = _latest_values(None, "price_technicals", "atr_pct", ["SPY"], date(2026, 9, 15))
    assert out == {"SPY": 2.5}
