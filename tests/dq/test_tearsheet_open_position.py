"""Tests for tearsheet equity / open-position carry."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
_spec = importlib.util.spec_from_file_location("generate_tearsheets", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_equity_and_trades = _mod.build_equity_and_trades
carry_open_at_period_end = _mod.carry_open_at_period_end


def test_carry_open_at_period_end() -> None:
    bars = [("2026-05-20", 100.0), ("2026-05-26", 90.0), ("2026-06-29", 80.0)]
    trades = [
        {
            "direction": "short",
            "entry_date": "2026-05-26",
            "entry_price": 90.0,
            "exit_date": "2026-06-29",
            "exit_price": 80.0,
        }
    ]
    carried = carry_open_at_period_end(trades, bars, "2026-01-01")
    assert carried[-1]["exit_date"] == ""
    assert carried[-1]["exit_price"] is None

    _, closed = build_equity_and_trades(carried, bars, 1000.0, "2026-01-01")
    assert closed[-1]["exit_reason"] == "open"
    assert closed[-1]["direction"] == "short"


def test_carry_open_skips_earlier_exit() -> None:
    bars = [("2026-05-20", 100.0), ("2026-05-26", 90.0), ("2026-06-29", 80.0)]
    trades = [
        {
            "direction": "long",
            "entry_date": "2026-05-20",
            "entry_price": 100.0,
            "exit_date": "2026-05-26",
            "exit_price": 90.0,
        },
        {
            "direction": "short",
            "entry_date": "2026-05-26",
            "entry_price": 90.0,
            "exit_date": "2026-06-29",
            "exit_price": 80.0,
        },
    ]
    carried = carry_open_at_period_end(trades, bars, "2026-01-01")
    assert carried[0]["exit_date"] == "2026-05-26"
    assert carried[-1]["exit_date"] == ""
