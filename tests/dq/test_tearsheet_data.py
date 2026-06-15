"""Unit tests for the unified tearsheet data contract (``tearsheet_data``).

No Nautilus required — both adapters are exercised with plain dicts so this
runs in the base (non-Nautilus) test environment.
"""

from __future__ import annotations

import json

import pytest

from digiquant.tearsheet_data import (
    SCHEMA_VERSION,
    TearsheetData,
    from_nautilus,
    from_pine,
)

pytestmark = pytest.mark.unit


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
