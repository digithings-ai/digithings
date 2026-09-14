"""Smoke test for the in-memory R2 market fixture (#4013).

``MemoryR2`` must serve the same surface the unmocked read path consumes:
SHA-verified generations plus the manifest seal used by freshness probes.
"""

from __future__ import annotations

import pytest
from digiquant.research.data.queries import r2_close_rows, r2_manifest_seal

from tests.fixtures.r2_market import build_r2_market

pytestmark = pytest.mark.unit


def test_fixture_serves_close_rows_and_seal(monkeypatch) -> None:
    store = build_r2_market(
        {"SPY": [{"date": "2026-09-10", "close": 100.0}, {"date": "2026-09-11", "close": 101.0}]},
        as_of="2026-09-11",
    )
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr("digiquant.mcp_server._get_r2_store", lambda: store)
    rows = r2_close_rows(tickers=["SPY"], since="2026-09-10", until="2026-09-11")
    assert [(r["date"], r["ticker"], r["close"]) for r in rows] == [
        ("2026-09-10", "SPY", 100.0),
        ("2026-09-11", "SPY", 101.0),
    ]
    seal, count = r2_manifest_seal()
    assert (seal.isoformat(), count) == ("2026-09-11", 1)
