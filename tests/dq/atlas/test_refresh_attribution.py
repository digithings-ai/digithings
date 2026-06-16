"""Attribution refresh runner (Pillar 3B).

The script reads positions + price_history window returns, runs the pure attribution core,
and upserts position_attribution. Loaded from its file path (lives under scripts/) and
exercised with a FakeSupabaseClient — no live Supabase.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "refresh_attribution.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("refresh_attribution_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


refresh_attribution_mod = _load_script()
AS_OF = date(2026, 6, 12)
START = "2026-05-22"  # AS_OF − 21 days


def _prices() -> list[dict]:
    # Two closes per ticker bracketing the 21-day window: AAPL +10%, TLT flat, SPY +5%.
    return [
        {"date": START, "ticker": "AAPL", "close": 100.0},
        {"date": "2026-06-12", "ticker": "AAPL", "close": 110.0},
        {"date": START, "ticker": "TLT", "close": 100.0},
        {"date": "2026-06-12", "ticker": "TLT", "close": 100.0},
        {"date": START, "ticker": "SPY", "close": 100.0},
        {"date": "2026-06-12", "ticker": "SPY", "close": 105.0},
    ]


def test_writes_reconciling_attribution() -> None:
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {
                    "date": "2026-06-12",
                    "ticker": "AAPL",
                    "weight_pct": 60,
                    "sector_bucket": "sector-technology",
                },
                {
                    "date": "2026-06-12",
                    "ticker": "TLT",
                    "weight_pct": 40,
                    "sector_bucket": "fixed-income",
                },
            ],
            "price_history": _prices(),
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 2  # AAPL + TLT, fully invested → no cash row
    assert reconciles is True
    rows = {r["ticker"]: r for r in client.store["position_attribution"]}
    assert rows["AAPL"]["selection_effect_pct"] == pytest.approx(3.0)  # 0.6×(10−5)
    assert rows["AAPL"]["_on_conflict"] == "date,ticker"
    assert rows["TLT"]["selection_effect_pct"] == pytest.approx(-2.0)  # 0.4×(0−5)


def test_missing_benchmark_skips() -> None:
    # No SPY price rows → benchmark return unknown → skip (retry next run), write nothing.
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [{"date": "2026-06-12", "ticker": "AAPL", "weight_pct": 100}],
            "price_history": [
                {"date": START, "ticker": "AAPL", "close": 100.0},
                {"date": "2026-06-12", "ticker": "AAPL", "close": 110.0},
            ],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 0
    assert reconciles is False
    assert "position_attribution" not in client.store


def test_no_positions_is_noop() -> None:
    client = FakeSupabaseClient(canned_reads={"positions": [], "price_history": _prices()})
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 0
    assert reconciles is True
    assert "position_attribution" not in client.store


def test_bad_date_returns_2(capsys) -> None:
    assert refresh_attribution_mod.main(["--date", "nope"]) == 2
    assert "bad --date" in capsys.readouterr().err
