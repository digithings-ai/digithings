"""Public signal delay for the tearsheet generator (#1462).

The public Slapper tearsheets lag reality by N calendar days via an END-DATE
SHIFT: ``generate_tearsheets.py --signal-delay-days N`` truncates the OHLCV
frame so the whole run ends N days before the freshest cached bar, and every
artifact (equity curve, drawdown, trade log, open-position state, headline
metrics) is derived from that shorter series — self-consistent by
construction, no redaction logic to get wrong. These tests cover the
date-shift arithmetic (``apply_signal_delay``), the default-0 no-op, the CLI
flag threading through ``main()``, and the ``signal_delay_days`` payload field
on the static JSON + index entry.

Tests that exercise ``run_and_write``/``main()`` need
``digiquant.strategies.calibrations_loader``, whose package ``__init__``
imports NautilusTrader — those are skipped when the extra isn't installed
(same reason the isolation tests are collect-ignored, see conftest).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from digiquant.tearsheet_data import TearsheetData, from_nautilus_run

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
_spec = importlib.util.spec_from_file_location("generate_tearsheets_signal_delay", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gts)

pytestmark = pytest.mark.unit

requires_nautilus = pytest.mark.skipif(
    importlib.util.find_spec("nautilus_trader") is None,
    reason="digiquant.strategies package __init__ imports nautilus_trader",
)


def _daily_frame(start: date, days: int) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(days)]
    n = len(dates)
    return pl.DataFrame(
        {
            "timestamp": dates,
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [1.0] * n,
        }
    )


# ---------------------------------------------------------------------------
# Date-shift arithmetic (apply_signal_delay)
# ---------------------------------------------------------------------------


def test_apply_signal_delay_shifts_end_date_back_n_days() -> None:
    df = _daily_frame(date(2024, 1, 1), 10)  # ends 2024-01-10
    out = gts.apply_signal_delay(df, 3)
    assert out.height == 7
    assert out["timestamp"].max() == date(2024, 1, 7)
    # Start of the series is untouched — only the end is shifted.
    assert out["timestamp"].min() == date(2024, 1, 1)


def test_apply_signal_delay_zero_is_exact_noop() -> None:
    df = _daily_frame(date(2024, 1, 1), 10)
    out = gts.apply_signal_delay(df, 0)
    assert out.equals(df)


def test_apply_signal_delay_negative_raises() -> None:
    df = _daily_frame(date(2024, 1, 1), 10)
    with pytest.raises(ValueError, match="signal_delay_days"):
        gts.apply_signal_delay(df, -1)


def test_apply_signal_delay_counts_calendar_days_not_bars() -> None:
    # Gap in the series (missing 2024-01-04/05): the cutoff is newest bar minus
    # N calendar days, so a 3-day delay from 2024-01-07 keeps only <= 2024-01-04.
    dates = [date(2024, 1, d) for d in (1, 2, 3, 6, 7)]
    df = pl.DataFrame({"timestamp": dates, "close": [1.0] * 5})
    out = gts.apply_signal_delay(df, 3)
    assert out["timestamp"].to_list() == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]


def test_apply_signal_delay_empty_frame_passthrough() -> None:
    df = _daily_frame(date(2024, 1, 1), 1).clear()
    assert gts.apply_signal_delay(df, 3).is_empty()


# ---------------------------------------------------------------------------
# Payload field (TearsheetData.signal_delay_days)
# ---------------------------------------------------------------------------


def _summary() -> dict:
    return {
        "strategy": "btc_slapper",
        "symbol": "BTC-USD",
        "period": "2020-01-01 → 2024-01-07",
        "bars": 100,
        "initial_capital": 1000.0,
        "final_equity": 1000.0,
        "net_profit_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "all": {"trades": 0},
    }


def test_payload_defaults_to_zero_delay() -> None:
    ts = from_nautilus_run(_summary(), [], equity_curve=[])
    assert ts.signal_delay_days == 0
    # Pre-1.2 payloads (no key) still validate to the 0 default.
    old = TearsheetData.model_validate({"strategy": "x", "symbol": "Y", "generated_at": "t"})
    assert old.signal_delay_days == 0


def test_payload_carries_signal_delay_days() -> None:
    ts = from_nautilus_run(_summary(), [], equity_curve=[], signal_delay_days=3)
    assert ts.signal_delay_days == 3
    payload = json.loads(ts.to_json())
    assert payload["signal_delay_days"] == 3
    assert TearsheetData.model_validate(payload).signal_delay_days == 3


def test_payload_rejects_negative_delay() -> None:
    with pytest.raises(ValueError):
        TearsheetData(strategy="x", symbol="Y", generated_at="t", signal_delay_days=-1)


# ---------------------------------------------------------------------------
# run_and_write: the shift flows into the backtest input and all outputs
# ---------------------------------------------------------------------------


class _NoPositions:
    """Stand-in for the Nautilus positions report — no round trips."""

    def iterrows(self) -> object:
        return iter(())


@requires_nautilus
def test_run_and_write_end_date_shift_flows_to_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import digiquant.data.prices.history_cache as history_cache
    import digiquant.strategies.calibrations_loader as cal_loader

    df = _daily_frame(date(2024, 1, 1), 10)  # cache ends 2024-01-10
    seen: dict[str, object] = {}

    def fake_run_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        seen["ohlcv"] = ohlcv
        bars_list = [
            (str(t)[:10], float(c))
            for t, c in zip(ohlcv["timestamp"].to_list(), ohlcv["close"].to_list())
        ]
        return _NoPositions(), bars_list, [], {}

    monkeypatch.setattr(history_cache, "load_cached", lambda symbol, cache_dir: df)
    monkeypatch.setattr(cal_loader, "resolve_calibrations", lambda *a, **k: {})
    monkeypatch.setattr(gts, "run_nautilus", fake_run_nautilus)

    settings = json.loads(gts.SETTINGS_PATH.read_text())
    settings["defaults"]["trade_start"] = ""  # keep the 2024 fixture window intact
    out_dir = tmp_path / "out"
    entry = gts.run_and_write(
        "btc_slapper",
        "BTC-USD",
        settings,
        tmp_path,
        out_dir,
        cal_source="example",
        signal_delay_days=3,
    )

    # The backtest itself ran on the truncated series — 3 days lopped off.
    shifted = seen["ohlcv"]
    assert isinstance(shifted, pl.DataFrame)
    assert shifted["timestamp"].max() == date(2024, 1, 7)

    # Static JSON payload: delay declared, period_end/equity curve shifted.
    payload = json.loads((out_dir / "btc_slapper.json").read_text())
    assert payload["signal_delay_days"] == 3
    assert payload["period_end"] == "2024-01-07"
    assert payload["equity_curve"][-1]["t"] == "2024-01-07"
    assert any("signal delay" in n.lower() for n in payload["notes"])

    # index.json entry mirrors the delayed view.
    assert entry is not None
    assert entry["signal_delay_days"] == 3
    assert entry["period_end"] == "2024-01-07"


@requires_nautilus
def test_run_and_write_default_is_undelayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import digiquant.data.prices.history_cache as history_cache
    import digiquant.strategies.calibrations_loader as cal_loader

    df = _daily_frame(date(2024, 1, 1), 10)

    def fake_run_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        bars_list = [
            (str(t)[:10], float(c))
            for t, c in zip(ohlcv["timestamp"].to_list(), ohlcv["close"].to_list())
        ]
        return _NoPositions(), bars_list, [], {}

    monkeypatch.setattr(history_cache, "load_cached", lambda symbol, cache_dir: df)
    monkeypatch.setattr(cal_loader, "resolve_calibrations", lambda *a, **k: {})
    monkeypatch.setattr(gts, "run_nautilus", fake_run_nautilus)

    settings = json.loads(gts.SETTINGS_PATH.read_text())
    settings["defaults"]["trade_start"] = ""
    out_dir = tmp_path / "out"
    entry = gts.run_and_write(
        "btc_slapper", "BTC-USD", settings, tmp_path, out_dir, cal_source="example"
    )

    payload = json.loads((out_dir / "btc_slapper.json").read_text())
    assert payload["signal_delay_days"] == 0
    assert payload["period_end"] == "2024-01-10"  # full series, nothing shifted
    assert entry is not None and entry["signal_delay_days"] == 0


# ---------------------------------------------------------------------------
# CLI flag threading: main() → run_strategy_isolated
# ---------------------------------------------------------------------------


def _capture_runner():
    seen: dict[str, int] = {}

    def runner(
        strategy: str,
        symbol: str,
        settings: dict,
        cache_dir: Path,
        output_dir: Path,
        *,
        cal_source: str,
        push_supabase: bool = False,
        signal_delay_days: int = 0,
    ) -> tuple[dict | None, str | None]:
        seen[strategy] = signal_delay_days
        return {"strategy": strategy}, None

    return runner, seen


def _main_argv(tmp_path: Path, out: Path, *extra: str) -> list[str]:
    return [
        "generate_tearsheets.py",
        "--allow-example-calibrations",
        "--cache-dir",
        str(tmp_path),
        "--output-dir",
        str(out),
        *extra,
    ]


def _patch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep main() hermetic: no .env load, no Supabase probing."""
    import digiquant.strategies.calibrations_loader as cal_loader

    monkeypatch.setattr(gts, "load_repo_env", lambda: None)
    monkeypatch.setattr(cal_loader, "pick_calibration_source", lambda **_: "example")


@requires_nautilus
def test_main_defaults_to_zero_delay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    runner, seen = _capture_runner()
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(sys, "argv", _main_argv(tmp_path, out))

    gts.main()

    assert seen and set(seen.values()) == {0}


@requires_nautilus
def test_main_threads_signal_delay_to_every_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    runner, seen = _capture_runner()
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(sys, "argv", _main_argv(tmp_path, out, "--signal-delay-days", "3"))

    gts.main()

    strategies = set(json.loads(gts.SETTINGS_PATH.read_text())["strategies"])
    assert set(seen) == strategies
    assert set(seen.values()) == {3}


@requires_nautilus
def test_main_rejects_negative_delay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "out"
    out.mkdir()
    runner, _ = _capture_runner()
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(sys, "argv", _main_argv(tmp_path, out, "--signal-delay-days", "-2"))

    with pytest.raises(SystemExit) as exc:
        gts.main()
    assert exc.value.code == 2  # argparse usage error
