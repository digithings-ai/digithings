"""Publish-path tests for btc_sdca (#3170)."""

from __future__ import annotations

import importlib.util
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
_spec = importlib.util.spec_from_file_location("generate_tearsheets_sdca_publish", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gts)

pytestmark = pytest.mark.unit

requires_nautilus = pytest.mark.skipif(
    importlib.util.find_spec("nautilus_trader") is None,
    reason="registry side-effect imports need nautilus_trader",
)

_EXAMPLE_COEFFS = (
    Path(__file__).resolve().parents[2]
    / "digiquant"
    / "src"
    / "digiquant"
    / "strategies"
    / "sdca"
    / "btc_power_law_coefficients.example.json"
)


def _daily_ohlcv(start: date, days: int, *, close0: float = 10_000.0) -> pl.DataFrame:
    dates = [start + timedelta(days=i) for i in range(days)]
    closes = [close0 * (1.001**i) for i in range(days)]
    return pl.DataFrame(
        {
            "timestamp": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1.0] * days,
            "symbol": ["BTC-USD"] * days,
        }
    )


def test_settings_btc_sdca_is_dca_family() -> None:
    settings = gts.load_settings()
    entry = settings["strategies"]["btc_sdca"]
    assert entry["symbol"] == "BTC-USD"
    assert entry["label"] == "BTC power-law remaining-book"
    assert entry["kind"] == "dca"
    assert gts.strategy_type_of(settings, "btc_sdca") == "sdca"
    assert gts.strategy_type_of(settings, "btc_slapper") == "slapper"
    sdca = entry["sdca"]
    assert sdca["long_only"] is False
    weights = sdca["indicator_weights"]
    catalog = ("weekly_rsi", "weekly_macd", "sma_band", "m2", "rs_eth", "dxy")
    assert set(catalog) <= set(weights)
    assert sdca["preset"] != "balanced"


def test_sdca_risk_index_uses_signal_delayed_frame_only(tmp_path: Path) -> None:
    """#1462: delayed OHLCV is the only input — no risk-index row after truncated end."""
    raw = _daily_ohlcv(date(2020, 1, 1), 30)
    delayed = gts.apply_signal_delay(raw, 5)
    assert delayed["timestamp"].max() < raw["timestamp"].max()
    out = tmp_path / "risk.parquet"
    index = gts.materialize_sdca_risk_index(delayed, out, coefficients_path=_EXAMPLE_COEFFS)
    end = delayed["timestamp"].max()
    if not isinstance(end, date):
        end = end.date()  # type: ignore[union-attr]
    assert index["date"].max() <= end
    assert index.filter(pl.col("date") > end).is_empty()
    assert out.exists()


def test_run_and_write_btc_sdca_skips_calibrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _daily_ohlcv(date(2020, 1, 1), 40).write_csv(cache / "BTC-USD.csv")
    output = tmp_path / "out"

    def _boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("resolve_calibrations must not run for strategy_type=sdca")

    import digiquant.strategies.calibrations_loader as cal_loader

    monkeypatch.setattr(cal_loader, "resolve_calibrations", _boom)

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        assert strategy == "btc_sdca"
        assert calibration is not None
        assert "risk_path" in calibration
        assert Path(calibration["risk_path"]).exists()
        ts = ohlcv["timestamp"].to_list()
        closes = ohlcv["close"].to_list()
        bars = [(str(t)[:10], float(c)) for t, c in zip(ts, closes, strict=True)]
        ohlc = [
            (str(t)[:10], float(c), float(c), float(c), float(c))
            for t, c in zip(ts, closes, strict=True)
        ]
        return _EmptyPositions(), bars, ohlc, {}, None

    monkeypatch.setattr(gts, "run_nautilus", _fake_nautilus)

    def _boom_round_trips(*_args: object, **_kwargs: object) -> list:
        raise AssertionError("sdca is not a round-trip book")

    monkeypatch.setattr(gts, "trades_from_positions", _boom_round_trips)
    settings = gts.load_settings()
    with caplog.at_level(logging.WARNING):
        entry = gts.run_and_write(
            "btc_sdca",
            "BTC-USD",
            settings,
            cache,
            output,
            cal_source="file",
            signal_delay_days=3,
        )
    assert entry is not None
    assert entry["kind"] == "dca"
    assert entry["win_rate_pct"] is None
    assert entry["profit_factor"] is None
    assert "vs_lump_pct" in entry
    payload = json.loads((output / "btc_sdca.json").read_text())
    assert payload["schema_version"] == "1.3"
    assert payload["dca"] is not None
    assert payload["win_rate_pct"] is None
    assert payload["profit_factor"] is None
    assert payload["long"] is None
    assert payload["short"] is None
    assert payload["kind"] == "dca"
    assert payload["current_signal"]["band"] in {
        "Fire sale",
        "Accumulate",
        "Value",
        "Above mid",
        "Hot",
        "Bubble",
    }
    assert "daily_rate_pct" in payload["current_signal"]
    assert "risk" in payload["current_signal"]
    assert payload["current_signal"]["entry_label"] != "MR Long"
    assert payload["rails"]
    assert payload["risk_curve"]
    assert payload["lump_equity_curve"]
    assert payload["flat_dca_equity_curve"]
    assert payload["capital_deployed_curve"]
    assert {"t", "low", "median", "high"} <= set(payload["rails"][0])
    assert "Coefficients" in " ".join(payload["notes"])
    assert "Preset btc_optimized" in " ".join(payload["notes"])
    assert "valuation:1.0" in " ".join(payload["notes"])
    assert "power-law remaining-book" in " ".join(payload["notes"]).lower()
    assert payload["beats_flat_dca_oos"] is False
    assert "beats_flat_dca_oos=false" in " ".join(payload["notes"])
    assert "not a live strategy" in " ".join(payload["notes"]).lower()
    assert not any("curve_simulator" in n.lower() for n in payload["notes"])
    assert not any("stage 1" in n.lower() for n in payload["notes"])
    assert payload["dca"]["allocated_pct"] is not None
    assert 0.0 <= payload["dca"]["allocated_pct"] <= 100.0
    assert "power-law only" in " ".join(payload["notes"]).lower()
    assert not any("calibrations.example" in rec.message for rec in caplog.records)
    assert not any("NOT production parity" in rec.message for rec in caplog.records)


def test_window_ohlcv_to_trade_start_drops_warmup_bars() -> None:
    raw = _daily_ohlcv(date(2017, 12, 1), 40)
    windowed = gts.window_ohlcv_to_trade_start(raw, "2018-01-01")
    assert windowed["timestamp"].min() >= date(2018, 1, 1)
    assert windowed["timestamp"].max() == raw["timestamp"].max()
    assert gts.window_ohlcv_to_trade_start(raw, "").height == raw.height


def test_run_and_write_windows_engine_bars_to_trade_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    _daily_ohlcv(date(2017, 12, 1), 50).write_csv(cache / "BTC-USD.csv")
    output = tmp_path / "out"
    captured: dict[str, object] = {}

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        captured["min"] = ohlcv["timestamp"].min()
        ts = ohlcv["timestamp"].to_list()
        closes = ohlcv["close"].to_list()
        bars = [(str(t)[:10], float(c)) for t, c in zip(ts, closes, strict=True)]
        ohlc = [
            (str(t)[:10], float(c), float(c), float(c), float(c))
            for t, c in zip(ts, closes, strict=True)
        ]
        return _EmptyPositions(), bars, ohlc, {}, None

    monkeypatch.setattr(gts, "run_nautilus", _fake_nautilus)
    settings = gts.load_settings()
    entry = gts.run_and_write(
        "btc_sdca",
        "BTC-USD",
        settings,
        cache,
        output,
        cal_source="file",
        signal_delay_days=0,
    )
    assert entry is not None
    assert captured["min"] is not None
    assert str(captured["min"])[:10] >= "2018-01-01"
    payload = json.loads((output / "btc_sdca.json").read_text())
    assert payload["period_start"] >= "2018-01-01"


@requires_nautilus
def test_trade_size_only_passed_when_config_declares_it() -> None:
    from digiquant.strategies.registry import config_declares_field, get_strategy
    from nautilus_trader.model import BarType
    from nautilus_trader.model.identifiers import InstrumentId

    assert config_declares_field("btc_slapper", "trade_size") is True
    assert config_declares_field("btc_sdca", "trade_size") is False

    inst = InstrumentId.from_str("BTC-USD.SIM")
    bar = BarType.from_str("BTC-USD.SIM-1-DAY-LAST-EXTERNAL")
    _, slapper_cfg = get_strategy("btc_slapper", inst, bar, trade_size=Decimal("1"))
    assert slapper_cfg.trade_size == Decimal("1")

    risk = Path("/tmp/sdca_publish_test_risk.parquet")
    _, sdca_cfg = get_strategy(
        "btc_sdca",
        inst,
        bar,
        trade_size=Decimal("99"),
        risk_path=str(risk),
    )
    assert not hasattr(sdca_cfg, "trade_size")
    assert sdca_cfg.risk_path == str(risk)
