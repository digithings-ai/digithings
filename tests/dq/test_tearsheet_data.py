"""Unit tests for the unified tearsheet data contract (``tearsheet_data``).

No Nautilus required — both adapters are exercised with plain dicts so this
runs in the base (non-Nautilus) test environment.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from digiquant.tearsheet_data import (
    SCHEMA_VERSION,
    OHLCBar,
    TearsheetData,
    from_nautilus,
    from_nautilus_run,
    from_pine,
)

pytestmark = pytest.mark.unit


def _load_generator():
    """Import the (non-package) tearsheet generator script by path.

    Nautilus imports are local to ``run_nautilus``, so importing the module is
    safe in the base test environment; only ``_entry_label`` is exercised here.
    """
    script = (
        Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
    )
    spec = importlib.util.spec_from_file_location("generate_tearsheets", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pine_summary() -> dict:
    block = {
        "trades": 4,
        "net_profit": 250.0,
        "net_profit_pct": 25.0,
        "gross_profit": 400.0,
        "gross_loss": -150.0,
        "percent_profitable": 75.0,
        "profit_factor": 2.6667,
        "avg_trade": 62.5,
        "wins": 3,
        "losses": 1,
    }
    return {
        "strategy": "btc_slapper",
        "symbol": "BTC-USD",
        "period": "2020-01-01 → 2021-01-01",
        "bars": 366,
        "initial_capital": 1000.0,
        "final_equity": 1250.0,
        "net_profit_pct": 25.0,
        "max_drawdown_pct": -12.5,
        "all": block,
        "long": {**block, "trades": 2, "net_profit": 200.0},
        "short": {**block, "trades": 2, "net_profit": 50.0},
    }


def _pine_trades() -> list[dict]:
    return [
        {
            "direction": "long",
            "entry_label": "MR Long",
            "entry_date": "2020-02-01",
            "entry_price": 100.0,
            "exit_date": "2020-03-01",
            "exit_price": 120.0,
            "qty": 10.0,
            "pnl": 200.0,
            "pnl_pct": 20.0,
            "equity_after": 1200.0,
            "exit_reason": "reversal",
            "max_runup_pct": 25.0,
            "max_drawdown_pct": -5.0,
        }
    ]


def test_from_pine_maps_headline_kpis() -> None:
    ts = from_pine(
        _pine_summary(),
        _pine_trades(),
        equity_curve=[("2020-01-01", 1000.0), ("2020-03-01", 1200.0)],
        data_source="Olympus price_history",
    )
    assert ts.schema_version == SCHEMA_VERSION
    assert ts.engine == "pine"
    assert ts.strategy == "btc_slapper"
    assert ts.symbol == "BTC-USD"
    assert ts.period_start == "2020-01-01"
    assert ts.period_end == "2021-01-01"
    assert ts.net_profit_pct == 25.0
    assert ts.win_rate_pct == 75.0
    assert ts.total_trades == 4
    assert ts.profit_factor == pytest.approx(2.6667)
    assert ts.data_source == "Olympus price_history"


def test_from_pine_directional_blocks() -> None:
    ts = from_pine(_pine_summary(), _pine_trades(), equity_curve=[])
    assert ts.long is not None and ts.short is not None
    assert ts.long.trades == 2
    assert ts.long.net_profit == 200.0
    assert ts.short.net_profit == 50.0


def test_drawdown_curve_is_derived_from_equity() -> None:
    # Equity dips from a peak of 1200 to 900 → -25% drawdown at the trough.
    eq = [("d1", 1000.0), ("d2", 1200.0), ("d3", 900.0), ("d4", 1100.0)]
    ts = from_pine(_pine_summary(), [], equity_curve=eq)
    dd = ts.drawdown_curve
    assert len(dd) == 4
    assert dd[0].v == pytest.approx(0.0)  # first bar is the peak
    assert dd[1].v == pytest.approx(0.0)  # new peak
    assert dd[2].v == pytest.approx(-25.0)  # 900 vs peak 1200
    assert dd[3].v == pytest.approx(-100.0 * (1200 - 1100) / 1200)


def test_to_json_roundtrips() -> None:
    ts = from_pine(_pine_summary(), _pine_trades(), equity_curve=[("d1", 1000.0)])
    payload = json.loads(ts.to_json())
    assert payload["strategy"] == "btc_slapper"
    assert payload["trades"][0]["direction"] == "long"
    assert payload["equity_curve"][0] == {"t": "d1", "v": 1000.0}
    # Re-validate to prove the serialized shape is contract-faithful.
    again = TearsheetData.model_validate(payload)
    assert again.total_trades == ts.total_trades


class _FakeResult:
    strategy_name = "ema_cross"
    symbols = ["ETH-USD"]
    start_time = "2021-01-01T00:00:00"
    end_time = "2022-01-01T00:00:00"
    total_pnl = 500.0
    total_return_pct = 50.0
    sharpe_ratio = 1.4
    max_drawdown_pct = -18.0
    num_trades = 12
    initial_capital = 1000.0


def test_from_nautilus_duck_types_result() -> None:
    ts = from_nautilus(_FakeResult(), data_source="unit")
    assert ts.engine == "nautilus"
    assert ts.strategy == "ema_cross"
    assert ts.symbol == "ETH-USD"  # first of symbols[]
    assert ts.sharpe_ratio == 1.4
    assert ts.net_profit == 500.0
    assert ts.final_equity == pytest.approx(1500.0)  # initial + pnl when no curve
    assert ts.total_trades == 12


# ── Schema 1.1: ohlc_bars + signal-type entry_label ──────────────────────────


def test_schema_version_is_1_2() -> None:
    assert SCHEMA_VERSION == "1.2"


def test_ohlc_bars_default_empty_and_back_compatible() -> None:
    # Adapters without OHLC (and 1.0 fixtures) leave ohlc_bars as [].
    ts = from_pine(_pine_summary(), _pine_trades(), equity_curve=[])
    assert ts.ohlc_bars == []
    # A 1.0-style payload (no ohlc_bars key) must still validate.
    again = TearsheetData.model_validate({"strategy": "x", "symbol": "Y", "generated_at": "t"})
    assert again.ohlc_bars == []


def test_ohlc_bars_roundtrip() -> None:
    bars = [("2020-01-01", 100.0, 110.0, 95.0, 105.0), ("2020-01-02", 105.0, 120.0, 104.0, 118.0)]
    ts = from_nautilus_run(
        _pine_summary(), _pine_trades(), equity_curve=[("2020-01-01", 1000.0)], ohlc_bars=bars
    )
    assert len(ts.ohlc_bars) == 2
    assert ts.ohlc_bars[0] == OHLCBar(t="2020-01-01", o=100.0, h=110.0, l=95.0, c=105.0)
    payload = json.loads(ts.to_json())
    assert payload["schema_version"] == "1.2"
    assert payload["ohlc_bars"][1] == {
        "t": "2020-01-02",
        "o": 105.0,
        "h": 120.0,
        "l": 104.0,
        "c": 118.0,
    }
    # Re-validate to prove the serialized shape is contract-faithful.
    again = TearsheetData.model_validate(payload)
    assert again.ohlc_bars[0].c == 105.0


@pytest.mark.parametrize(
    ("signal_type", "direction", "expected"),
    [
        ("mean_reversion", "long", "MR Long"),
        ("mean_reversion", "short", "MR Short"),
        ("trend", "long", "Trend Long"),
        ("trend", "short", "Trend Short"),
        ("trend+mr", "long", "MR&T Long"),
        ("trend+mr", "short", "MR&T Short"),
        ("reversal", "long", "Reversal Long"),
        ("reversal", "short", "Reversal Short"),
        (None, "long", ""),  # join miss → blank, no crash
        ("", "short", ""),  # blank type → blank
        ("bogus", "long", ""),  # unknown type → blank
    ],
)
def test_entry_label_mirrors_pine_taxonomy(signal_type, direction, expected) -> None:
    gen = _load_generator()
    assert gen._entry_label(signal_type, direction) == expected
