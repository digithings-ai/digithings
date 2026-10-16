"""R2-only market reads for backfill_context (#4053 Task 4).

``fetch_context`` reads prices/technicals from the sealed R2 generations
(``r2_close_rows`` / ``r2_ohlcv_rows`` / ``get_price_technicals`` — the
technicals helper is R2-only since #4053). Macro series and snapshots stay on
Supabase (D2), so the function still builds a client through ``_sb`` — the
``fake_sb`` fixture keeps these unit tests off a real one. Loaded via
``importlib.util`` like the other script-level tests (``digiquant/scripts/`` is
not an installed package).
"""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — script modules loaded by path

import pytest

from tests.fixtures.fake_supabase import FakeSupabaseClient

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]

pytestmark = pytest.mark.unit

_RESEARCH_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "research"


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _RESEARCH_SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bc = _load("backfill_context_r2", "backfill_context.py")


@pytest.fixture(autouse=True)
def fake_sb(monkeypatch: pytest.MonkeyPatch) -> FakeSupabaseClient:
    """Install an in-memory client as ``_sb``; seed ``canned_reads`` to serve rows."""
    client = FakeSupabaseClient()
    monkeypatch.setattr(bc, "_sb", lambda: client)
    return client


def test_latest_price_date_and_technicals_from_r2(r2_market, monkeypatch) -> None:
    r2_market(
        {
            "SPY": [
                {
                    "date": "2026-09-10",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10,
                }
            ],
        },
        as_of="2026-09-10",
    )
    monkeypatch.setattr(bc, "CORE_TICKERS", {"SPY"})
    ctx = bc.fetch_context("2026-09-10")
    assert ctx["latest_price_date"] == "2026-09-10"
    assert ctx["prices"] and ctx["prices"][0]["ticker"] == "SPY"


def test_r2_price_rows_carry_supabase_indicator_keys_and_prompt_renders(
    r2_market, monkeypatch
) -> None:
    rows = [
        {
            "date": f"2026-09-{day:02d}",
            "open": 100.0 + day,
            "high": 101.0 + day,
            "low": 99.0 + day,
            "close": 100.0 + day + 0.5,
            "volume": 10,
        }
        for day in range(4, 11)
    ]
    r2_market({"SPY": rows, "QQQ": rows, "GLD": rows}, as_of="2026-09-10")
    monkeypatch.setattr(bc, "CORE_TICKERS", ["SPY", "QQQ", "GLD"])
    ctx = bc.fetch_context("2026-09-10")

    indicator_keys = (
        "sma_20",
        "sma_50",
        "sma_200",
        "rsi_14",
        "macd",
        "macd_signal",
        "roc_5",
        "roc_21",
        "bb_pct_b",
        "zscore_50",
        "atr_pct",
        "hist_vol_21",
    )
    assert [row["ticker"] for row in ctx["prices"]] == ["GLD", "QQQ", "SPY"]
    for row in ctx["prices"]:
        assert all(key in row for key in indicator_keys), row
        # No R2 equivalent for these names — absent stays None, never a
        # different-window substitute (e.g. `macd_hist` into `macd`).
        assert row["sma_20"] is None and row["macd"] is None and row["zscore_50"] is None

    prompt = bc.build_agent_prompt(ctx)
    assert "Price & Technical Indicators" in prompt
    spy_line = next(line for line in prompt.splitlines() if line.startswith("| SPY |"))
    assert "—" in spy_line


def test_r2_context_keeps_macro_and_snapshots_on_supabase(r2_market, monkeypatch, fake_sb) -> None:
    """D2: only market/price data moves to R2 — macro and snapshots stay on Supabase.

    The prompt must not claim a false "first run": with the canned Supabase rows the
    R2 context carries the real prior/baseline dates and a non-empty macro block, and
    overlapping indicators (rsi_14) still flow from the R2 technicals envelope.
    """
    bars = [
        {
            "date": (date(2026, 8, 12) + timedelta(days=offset)).isoformat(),
            "open": 100.0 + offset,
            "high": 101.0 + offset,
            "low": 99.0 + offset,
            "close": 100.0 + offset,
            "volume": 10,
        }
        for offset in range(30)
    ]
    r2_market({"SPY": bars}, as_of="2026-09-10")
    fake_sb.canned_reads = {
        "macro_series_observations": [
            {
                "series_id": "DGS10",
                "source": "fred",
                "obs_date": "2026-09-09",
                "value": 4.2,
                "unit": "percent",
                "meta": None,
            }
        ],
        "daily_snapshots": [
            {
                "date": "2026-09-09",
                "run_type": "daily",
                "baseline_date": "2026-09-06",
                "snapshot": {
                    "regime": {"bias": "neutral", "label": "range"},
                    "portfolio": {
                        "posture": "balanced",
                        "cash_pct": 10,
                        "positions": [
                            {
                                "ticker": "SPY",
                                "weight_pct": 20,
                                "action": "HOLD",
                                "rationale": "core",
                            }
                        ],
                    },
                    "theses": [{"id": "T1", "name": "core", "status": "active"}],
                    "actionable": ["watch CPI"],
                },
            },
            {
                "date": "2026-09-06",
                "run_type": "baseline",
                "snapshot": {"regime": {"bias": "neutral", "label": "range"}},
            },
        ],
    }
    monkeypatch.setattr(bc, "CORE_TICKERS", ["SPY"])
    ctx = bc.fetch_context("2026-09-10")

    assert set(ctx) == {
        "as_of_date",
        "latest_price_date",
        "prior_snapshot_date",
        "baseline_date",
        "prices",
        "macro_series",
        "prior_snapshot",
        "baseline_snapshot",
    }
    assert ctx["macro_series"]["fred:DGS10"]["value"] == 4.2
    assert ctx["prior_snapshot"] and ctx["prior_snapshot_date"] == "2026-09-09"
    assert ctx["baseline_snapshot"] and ctx["baseline_date"] == "2026-09-06"
    assert any(row.get("rsi_14") is not None for row in ctx["prices"])

    prompt = bc.build_agent_prompt(ctx)
    assert "DGS10" in prompt
    assert "**Prior regime:** neutral — range" in prompt
    assert "No prior snapshot found" not in prompt
