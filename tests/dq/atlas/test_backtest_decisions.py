"""Decision-backtest runner (Pillar 3C).

build_trades turns decision_log rows into realized trades via query_returns_window (mocked
here — no live prices), skipping non-long stances + decisions whose window isn't available.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "backtest_decisions.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("backtest_decisions_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backtest_mod = _load_script()


def _fake_returns_window(returns_by_ticker):
    def _qrw(*, client, ticker, start_date, holding_days, lookback_days=21):
        value = returns_by_ticker.get(ticker)
        return (value, start_date, start_date) if value is not None else None

    return _qrw


def test_build_trades_filters_and_maps(monkeypatch) -> None:
    import digiquant.olympus.atlas.supabase_io as sio

    monkeypatch.setattr(
        sio,
        "query_returns_window",
        _fake_returns_window({"AAPL": 0.10, "TLT": 0.02, "SPY": 0.05}),
    )
    decisions = [
        {
            "run_date": "2026-05-01",
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 5,
            "holding_days": 5,
        },
        {
            "run_date": "2026-05-02",
            "ticker": "XOM",
            "stance": "sell",
            "conviction": 3,
            "holding_days": 5,
        },
        {
            "run_date": "2026-05-03",
            "ticker": "TLT",
            "stance": "hold",
            "conviction": 2,
            "holding_days": 5,
        },
    ]
    trades = backtest_mod.build_trades(client=object(), decisions=decisions)
    # sell is dropped (not long-side); buy + hold kept.
    assert {t.ticker for t in trades} == {"AAPL", "TLT"}
    aapl = next(t for t in trades if t.ticker == "AAPL")
    assert aapl.return_frac == pytest.approx(0.10)
    assert aapl.benchmark_frac == pytest.approx(0.05)  # SPY default benchmark
    assert aapl.conviction == 5


def test_build_trades_skips_unpriced_window(monkeypatch) -> None:
    import digiquant.olympus.atlas.supabase_io as sio

    # AAPL has a window but SPY (benchmark) does not → the decision is skipped.
    monkeypatch.setattr(sio, "query_returns_window", _fake_returns_window({"AAPL": 0.10}))
    decisions = [
        {
            "run_date": "2026-05-01",
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 5,
            "holding_days": 5,
        }
    ]
    assert backtest_mod.build_trades(client=object(), decisions=decisions) == []


def test_bad_start_returns_2(capsys) -> None:
    assert backtest_mod.main(["--start", "nope"]) == 2
    assert "bad --start" in capsys.readouterr().err
