"""Current-book lookback refresh runner (#2598; R2-only market reads, #4053).

The script reads positions + sealed R2 window returns, runs the pure lookback core,
and upserts ``current_book_lookback``. Market data comes from the in-memory R2
fixture (no Supabase market body, no network); positions/writes use a
FakeSupabaseClient. Loaded from its file path (lives under scripts/).
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from tests.dq.research.test_supabase_io import FakeSupabaseClient

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
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

# Two closes per ticker bracketing the 21-day window: AAPL +10%, TLT flat, SPY +5%.
_MARKET_ROWS: dict[str, list[dict]] = {
    "AAPL": [{"date": START, "close": 100.0}, {"date": "2026-06-12", "close": 110.0}],
    "TLT": [{"date": START, "close": 100.0}, {"date": "2026-06-12", "close": 100.0}],
    "SPY": [{"date": START, "close": 100.0}, {"date": "2026-06-12", "close": 105.0}],
}


def _arm_market(r2_market, tickers: tuple[str, ...] = ("AAPL", "TLT", "SPY")) -> None:
    """Seal one R2 generation per requested ticker; an absent ticker is unknown."""
    r2_market({ticker: _MARKET_ROWS[ticker] for ticker in tickers}, as_of="2026-06-12")


def test_writes_reconciling_lookback_with_explicit_labels(r2_market) -> None:
    _arm_market(r2_market)
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
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 2  # AAPL + TLT, fully invested → no cash row
    assert reconciles is True
    assert "position_attribution" not in client.store
    rows = {r["ticker"]: r for r in client.store["current_book_lookback"]}
    assert rows["AAPL"]["selection_effect_pct"] == pytest.approx(3.0)  # 0.6×(10−5)
    assert rows["AAPL"]["_on_conflict"] == "date,ticker"
    assert rows["TLT"]["selection_effect_pct"] == pytest.approx(-2.0)  # 0.4×(0−5)
    assert rows["AAPL"]["contract"] == "current_book_lookback"
    assert rows["AAPL"]["lookback_days"] == 21
    assert rows["AAPL"]["window_start_date"] == START
    assert rows["AAPL"]["window_end_date"] == "2026-06-12"


def test_rerun_is_idempotent_upsert(r2_market) -> None:
    _arm_market(r2_market)
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {
                    "date": "2026-06-12",
                    "ticker": "AAPL",
                    "weight_pct": 100,
                    "sector_bucket": "sector-technology",
                },
            ],
        }
    )
    w1, _ = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    w2, _ = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert w1 == w2 == 1
    # Fake client appends on upsert; conflict key is stable — real DB upserts in place.
    assert all(r["_on_conflict"] == "date,ticker" for r in client.store["current_book_lookback"])


def test_missing_benchmark_skips(r2_market) -> None:
    # No SPY generation → benchmark return unknown → skip (retry next run), write nothing.
    _arm_market(r2_market, tickers=("AAPL",))
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [{"date": "2026-06-12", "ticker": "AAPL", "weight_pct": 100}],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 0
    assert reconciles is False
    assert "current_book_lookback" not in client.store


def test_no_positions_is_noop(r2_market) -> None:
    # The date was never materialized (no positions rows at all) → genuine no-op.
    _arm_market(r2_market)
    client = FakeSupabaseClient(canned_reads={"positions": []})
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 0
    assert reconciles is True
    assert "current_book_lookback" not in client.store


def test_all_cash_day_writes_cash_row(r2_market) -> None:
    # A fully-in-cash day (only a CASH position row) still produces a CASH lookback row
    # with the cash-drag allocation effect (−1.0 × benchmark return).
    _arm_market(r2_market, tickers=("SPY",))
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [{"date": "2026-06-12", "ticker": "CASH", "weight_pct": 100}],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 1
    assert reconciles is True
    cash = client.store["current_book_lookback"][0]
    assert cash["ticker"] == "CASH"
    assert cash["allocation_effect_pct"] == pytest.approx(-5.0)  # −1.0 × 5% benchmark
    assert cash["contract"] == "current_book_lookback"


def test_house_book_ignores_same_date_overlay_positions(r2_market) -> None:
    from digiquant.dashboard.tenancy import house_workspace_id

    _arm_market(r2_market)
    overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    house = str(house_workspace_id())
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {
                    "date": "2026-06-12",
                    "ticker": "AAPL",
                    "weight_pct": 100,
                    "sector_bucket": "sector-technology",
                    "workspace_id": house,
                },
                {
                    "date": "2026-06-12",
                    "ticker": "OVERLAY",
                    "weight_pct": 99,
                    "sector_bucket": "sector-overlay",
                    "workspace_id": overlay,
                },
            ],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 1
    assert reconciles is True
    rows = {r["ticker"]: r for r in client.store["current_book_lookback"]}
    assert "AAPL" in rows
    assert "OVERLAY" not in rows


def test_overlay_only_positions_are_noop_for_house_lookback(r2_market) -> None:
    _arm_market(r2_market)
    overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {
                    "date": "2026-06-12",
                    "ticker": "OVERLAY",
                    "weight_pct": 100,
                    "workspace_id": overlay,
                },
            ],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 0
    assert reconciles is True
    assert "current_book_lookback" not in client.store


def test_unknown_ticker_is_an_unpriced_holding_not_an_outage(r2_market) -> None:
    """A holding with no R2 generation renders PARTIAL (None return), not a crash (#4053)."""
    _arm_market(r2_market, tickers=("AAPL", "SPY"))
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {"date": "2026-06-12", "ticker": "AAPL", "weight_pct": 60},
                {"date": "2026-06-12", "ticker": "MISSING", "weight_pct": 40},
            ],
        }
    )
    written, reconciles = refresh_attribution_mod.refresh_attribution(client=client, as_of=AS_OF)
    assert written == 2
    assert reconciles is False  # MISSING has no return window


def test_bad_date_returns_2(capsys) -> None:
    assert refresh_attribution_mod.main(["--date", "nope"]) == 2
    assert "bad --date" in capsys.readouterr().err
