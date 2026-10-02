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


def _daily_ohlcv(
    start: date, days: int, *, close0: float = 10_000.0, symbol: str = "BTC-USD"
) -> pl.DataFrame:
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
            "symbol": [symbol] * days,
        }
    )


def test_settings_btc_sdca_is_dca_family() -> None:
    settings = gts.load_settings()
    entry = settings["strategies"]["btc_sdca"]
    assert entry["symbol"] == "BTC-USD"
    assert entry["label"] == "BTC-SDCA"
    assert entry["kind"] == "dca"
    assert gts.strategy_type_of(settings, "btc_sdca") == "sdca"
    assert gts.strategy_type_of(settings, "btc_slapper") == "slapper"
    assert settings["strategies"]["btc_slapper"]["label"] == "BTC L/S"
    assert settings["strategies"]["eth_slapper"]["label"] == "ETH L/S"
    assert settings["strategies"]["sol_slapper"]["label"] == "SOL L/S"
    sdca = entry["sdca"]
    assert sdca["long_only"] is False
    weights = sdca["indicator_weights"]
    catalog = ("weekly_rsi", "weekly_macd", "sma_band", "m2", "rs_eth", "dxy")
    assert set(catalog) <= set(weights)
    assert weights["valuation"] == 1.0
    assert weights["m2"] == 0.5
    assert weights["dxy"] == 0.5
    assert weights["rs_eth"] == 0.0
    assert weights["weekly_rsi"] == 0.25
    assert weights["weekly_macd"] == 0.5
    assert weights["sma_band"] == 0.0
    assert sdca["preset"] != "balanced"


def test_catalog_row_from_settings_registers_btc_sdca() -> None:
    settings = gts.load_settings()
    row = gts.catalog_row_from_settings(settings, "btc_sdca")
    assert row["id"] == "btc_sdca"
    assert row["symbol"] == "BTC-USD"
    assert row["label"] == "BTC-SDCA"
    assert row["engine"] == "nautilus"
    assert row["enabled"] is True
    assert row["config"]["kind"] == "dca"
    assert row["config"]["strategy_type"] == "sdca"
    slapper = gts.catalog_row_from_settings(settings, "btc_slapper")
    assert slapper["config"]["kind"] == "long_short"
    assert slapper["config"]["strategy_type"] == "slapper"


def test_richer_composite_sidecar_matches_settings() -> None:
    sidecar = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "digiquant/src/digiquant/strategies/sdca/btc_richer_composite.json"
        ).read_text()
    )
    settings = gts.load_settings()
    published = settings["strategies"]["btc_sdca"]["sdca"]["indicator_weights"]
    assert sidecar["beats_flat_dca_oos"] is False
    assert sidecar["published_weights"] == published
    assert sidecar["public_name"] == "BTC-SDCA"


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
    # Oscillators need ~15 completed weeks before they vote; a 40-day frame
    # would null the whole composite via the all-nulls rule.
    _daily_ohlcv(date(2020, 1, 1), 300).write_csv(cache / "BTC-USD.csv")
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
    assert payload["schema_version"] == "1.4"
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
    assert "composite valuation index" in " ".join(payload["notes"]).lower()
    assert "weekly log-MACD" in " ".join(payload["notes"])
    assert "weekly RSI" in " ".join(payload["notes"])
    assert payload["beats_flat_dca_oos"] is False
    assert "beats_flat_dca_oos=false" in " ".join(payload["notes"])
    assert "not a live strategy" in " ".join(payload["notes"]).lower()
    assert "Buy-and-hold" in " ".join(payload["notes"])
    assert not any(
        "curve_simulator" in n.lower() and "beats_flat_dca_oos=true" in n.lower()
        for n in payload["notes"]
    )
    assert not any("stage 1" in n.lower() and "persist" in n.lower() for n in payload["notes"])
    assert payload["dca"]["allocated_pct"] is not None
    assert 0.0 <= payload["dca"]["allocated_pct"] <= 100.0
    assert "power-law only" not in " ".join(payload["notes"]).lower()
    assert "not a multi-indicator composite" not in " ".join(payload["notes"]).lower()
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


def test_run_and_write_per_entry_trade_start_gold_override_btc_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per-entry trade_start override, Ruling 5 (#4804): gold resolves its
    entry-level 2010-01-01 window while BTC entries without the key fall back
    to defaults (2018-01-01) byte-identically.

    Mirrors the sell_mask BTC-None paired pattern: the gold arm proves the
    override takes effect (engine bars start 2010, strictly before the
    default), the BTC arm proves the fallback is undisturbed.
    """
    import digiquant.strategies.sdca.providers as providers_mod

    cache = tmp_path / "cache"
    cache.mkdir()
    start, days = date(2009, 6, 1), 3400
    _daily_ohlcv(start, days, close0=100.0, symbol="GLD-USD").write_csv(cache / "GLD-USD.csv")
    _daily_ohlcv(start, days, close0=10_000.0, symbol="BTC-USD").write_csv(cache / "BTC-USD.csv")
    output = tmp_path / "out"
    captured: dict[str, object] = {}

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        captured[strategy] = ohlcv["timestamp"].min()
        ts = ohlcv["timestamp"].to_list()
        closes = ohlcv["close"].to_list()
        bars = [(str(t)[:10], float(c)) for t, c in zip(ts, closes, strict=True)]
        ohlc = [
            (str(t)[:10], float(c), float(c), float(c), float(c))
            for t, c in zip(ts, closes, strict=True)
        ]
        return _EmptyPositions(), bars, ohlc, {}, None

    monkeypatch.setattr(gts, "run_nautilus", _fake_nautilus)

    class _StubRiskModel:
        def __init__(self) -> None:
            from types import SimpleNamespace

            self.coefficients = SimpleNamespace(
                fit_start=start, fit_end=start + timedelta(days=days - 1), fit_rows=days
            )

        def rails(self, dates):  # type: ignore[no-untyped-def]
            n = len(dates)
            return pl.DataFrame({"low": [90.0] * n, "median": [100.0] * n, "high": [110.0] * n})

    def _fake_resolve(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
        return _StubRiskModel()

    monkeypatch.setattr(providers_mod, "resolve_sdca_risk_model", _fake_resolve)

    settings = gts.load_settings()
    assert settings["strategies"]["gold_sdca"].get("trade_start") == "2010-01-01"
    assert "trade_start" not in settings["strategies"]["btc_sdca"]

    gold_entry = gts.run_and_write(
        "gold_sdca", "GLD-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    btc_entry = gts.run_and_write(
        "btc_sdca", "BTC-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert gold_entry is not None
    assert btc_entry is not None
    assert str(captured["gold_sdca"])[:10] == "2010-01-01"
    assert str(captured["gold_sdca"])[:10] < "2018-01-01"
    assert str(captured["btc_sdca"])[:10] == "2018-01-01"


def test_run_and_write_gold_sdca_dispatches_rolling_z_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gold live-path plumbing (#4804): entry-driven dispatch, no live fit.

    Canned ``gold_sdca``-shaped run through ``run_and_write`` with the rails
    seam stubbed (assert dispatch *name*, not fit values) and only a UUP
    sibling staged: uup must survive the drop-guard while the unstaged m2 leg
    is zeroed, and provenance must name uup + the rolling-z risk model
    (Ruling 4: the reselect rides rolling90/z1.0 rails, not generic trend).
    """
    from types import SimpleNamespace

    import digiquant.strategies.sdca.providers as providers_mod

    cache = tmp_path / "cache"
    cache.mkdir()
    start, days = date(2020, 1, 1), 300
    _daily_ohlcv(start, days, close0=2500.0, symbol="GLD-USD").write_csv(cache / "GLD-USD.csv")
    uup_dates = [start + timedelta(days=i) for i in range(days)]
    pl.DataFrame({"date": uup_dates, "value": [28.0 * (1.0005**i) for i in range(days)]}).write_csv(
        cache / "UUP.csv"
    )
    output = tmp_path / "out"

    resolved_names: list[str] = []

    class _StubRiskModel:
        """Canned corridor rails; provenance shaped like a real fit."""

        def __init__(self) -> None:
            self.coefficients = SimpleNamespace(
                fit_start=start, fit_end=start + timedelta(days=days - 1), fit_rows=days
            )

        def rails(self, dates):  # type: ignore[no-untyped-def]
            n = len(dates)
            return pl.DataFrame({"low": [90.0] * n, "median": [100.0] * n, "high": [110.0] * n})

    def _fake_resolve(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
        resolved_names.append(name)
        return _StubRiskModel()

    monkeypatch.setattr(providers_mod, "resolve_sdca_risk_model", _fake_resolve)

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    captured: dict[str, object] = {}

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        assert strategy == "gold_sdca"
        assert symbol == "GLD-USD"
        assert calibration is not None
        assert "risk_path" in calibration
        assert Path(calibration["risk_path"]).exists()
        captured["indicator_weights"] = calibration["indicator_weights"]
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
        "gold_sdca",
        "GLD-USD",
        settings,
        cache,
        output,
        cal_source="file",
        signal_delay_days=0,
    )
    assert entry is not None
    assert entry["kind"] == "dca"
    # Rails dispatch reads the entry's risk_model (no live fit in tests).
    assert resolved_names == ["rolling_z"]
    # Drop-guard: staged uup survives, unstaged m2 is zeroed.
    published = settings["strategies"]["gold_sdca"]["sdca"]["indicator_weights"]
    assert published["uup"] == 0.5
    kept = captured["indicator_weights"]
    assert isinstance(kept, dict)
    assert kept.get("uup") == 0.5
    assert kept.get("m2") == 0.0
    payload = json.loads((output / "gold_sdca.json").read_text())
    notes = " ".join(payload["notes"])
    assert "uup:0.5" in notes
    assert "risk_model=rolling_z" in notes
    assert "Preset gold_reselect" in notes
    assert "Coefficients" in notes
    assert payload["dca"] is not None
    assert payload["kind"] == "dca"


@requires_nautilus
def test_trade_size_only_passed_when_config_declares_it() -> None:
    from digiquant.strategies.registry import config_declares_field, get_strategy
    from nautilus_trader.model import BarType
    from nautilus_trader.model.identifiers import InstrumentId

    assert config_declares_field("btc_slapper", "trade_size") is True
    assert config_declares_field("btc_sdca", "trade_size") is False
    assert config_declares_field("btc_sdca", "preset") is False
    assert config_declares_field("btc_sdca", "indicator_weights") is False
    assert config_declares_field("btc_sdca", "risk_path") is True

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


@requires_nautilus
def test_gold_sdca_registry_resolves_v3_nodes_and_btc_undisturbed() -> None:
    """Registry gap net (#4804): gold resolves to honest-v3 nodes; btc untouched.

    The Task-1 offline gold test fakes ``run_nautilus``, so it structurally
    cannot catch a missing registry entry (Task-3 STOP). This test exercises
    the real registry: ``gold_sdca`` must resolve to the v3 gated curve
    (shape 35/45/50/30/1.0/2.0, mids null) and the staged ``gold_optimized``
    preset nodes, while ``btc_sdca`` resolution is byte-identical.
    The full unfaked live path is proven by the Task-3 proof command re-run,
    not duplicated here (engine-run harness + Nautilus version drift cost).
    """
    import digiquant.strategies.sdca.nautilus_strategy  # noqa: F401  # side-effect register
    from digiquant.strategies.registry import config_declares_field, get_strategy
    from digiquant.strategies.sdca.curve import DEFAULT_BTC_NODES
    from digiquant.strategies.sdca.presets import load_preset
    from digiquant.strategy_specs import get_param_specs
    from nautilus_trader.model import BarType
    from nautilus_trader.model.identifiers import InstrumentId

    # Staged preset shape is the honest-v3 gated shape (read, never re-derived
    # here beyond this pin).
    preset = load_preset("gold_optimized")
    assert preset.shape is not None
    assert preset.shape.model_dump() == {
        "buy_max_rate": 35.0,
        "buy_knee_risk": 45.0,
        "sell_knee_risk": 50.0,
        "sell_max_rate": 30.0,
        "buy_curvature": 1.0,
        "sell_curvature": 2.0,
        "buy_mid_knee_risk": None,
        "buy_mid_curvature": 1.0,
        "sell_mid_knee_risk": None,
        "sell_mid_curvature": 1.0,
    }

    assert config_declares_field("gold_sdca", "trade_size") is False
    assert config_declares_field("gold_sdca", "risk_path") is True

    inst = InstrumentId.from_str("GLD-USD.SIM")
    bar = BarType.from_str("GLD-USD.SIM-1-DAY-LAST-EXTERNAL")
    risk = Path("/tmp/sdca_publish_test_risk_gold.parquet")
    _, gold_cfg = get_strategy(
        "gold_sdca",
        inst,
        bar,
        trade_size=Decimal("99"),
        risk_path=str(risk),
    )
    assert not hasattr(gold_cfg, "trade_size")
    assert gold_cfg.risk_path == str(risk)
    assert tuple(gold_cfg.curve_nodes) == preset.curve_nodes
    assert gold_cfg.long_only is False
    assert gold_cfg.initial_cash == 1000.0

    # Paired parity assert: btc resolution undisturbed.
    btc_inst = InstrumentId.from_str("BTC-USD.SIM")
    btc_bar = BarType.from_str("BTC-USD.SIM-1-DAY-LAST-EXTERNAL")
    _, btc_cfg = get_strategy(
        "btc_sdca",
        btc_inst,
        btc_bar,
        trade_size=Decimal("99"),
        risk_path=str(risk),
    )
    assert tuple(btc_cfg.curve_nodes) == DEFAULT_BTC_NODES
    assert tuple(gold_cfg.curve_nodes) != tuple(btc_cfg.curve_nodes)

    # Optimize/export param-spec path resolves gold to the shared sdca specs.
    assert get_param_specs("gold_sdca") == get_param_specs("btc_sdca")


def test_settings_gold_sdca_sell_mask_strict_box() -> None:
    """Gold entry carries the frozen strict-box sell-mask spec (#4804).

    BTC entries gain nothing (no ``sell_mask`` key anywhere else).
    """
    from build_gold_sell_mask import FROZEN_M_THRESH, FROZEN_Z_THRESH

    settings = gts.load_settings()
    sdca = settings["strategies"]["gold_sdca"]["sdca"]
    mask = sdca["sell_mask"]
    assert mask["z_thresh"] == FROZEN_Z_THRESH == -2.0
    assert mask["m_thresh"] == FROZEN_M_THRESH == 1.5
    assert mask["z_window"] == 1260
    assert mask["sma_window"] == 1000
    assert "sell_mask" not in settings["strategies"]["btc_sdca"].get("sdca", {})
    assert "sell_mask" not in settings["strategies"]["btc_slapper"]


def test_run_and_write_gold_sell_mask_threads_veto_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Masked gold-shaped entry through the live path with stubbed seams (#4804).

    Mirror of the Plan-11 dispatch test: rails seam stubbed, engine seam
    stubbed, but the mask itself is the SHIPPED builder on staged inputs
    (strict box values). Asserts: the builder ran with strict thresholds,
    ``sell_dates`` reach the strategy overrides (calibration), provenance
    names the mask-day count. Paired BTC run resolves mask None with the
    same calibration key set (modulo ``sell_dates``) and no mask note.
    """
    import copy

    import build_gold_sell_mask as mask_mod
    import digiquant.strategies.sdca.providers as providers_mod

    cache = tmp_path / "cache"
    cache.mkdir()
    start, days = date(2020, 1, 1), 300
    step_at = 280
    # Drifted (not flat) closes with the 2x jump preserved: the promoted
    # entry carries nonzero oscillator weights, and flat stretches give
    # zero-variance windows → non-finite extras → risk-index rejection.
    # Drift keeps every window finite; the jump still drives the m-leg.
    gld_closes = [
        (100.0 * (1.001**i)) if i < step_at else (200.0 * (1.001**i)) for i in range(days)
    ]
    gld_dates = [start + timedelta(days=i) for i in range(days)]
    pl.DataFrame(
        {
            "timestamp": [d.isoformat() for d in gld_dates],
            "open": gld_closes,
            "high": gld_closes,
            "low": gld_closes,
            "close": gld_closes,
            "volume": [1.0] * days,
            "symbol": ["GLD-USD"] * days,
        }
    ).write_csv(cache / "GLD-USD.csv")
    _daily_ohlcv(start, days, close0=10_000.0, symbol="BTC-USD").write_csv(cache / "BTC-USD.csv")
    with (cache / "DFII10.csv").open("w") as f:
        f.write("observation_date,DFII10\n")
        for i in range(days):
            f.write(f"{(start + timedelta(days=i)).isoformat()},{2.0 if i < step_at else -3.0}\n")
    pl.DataFrame({"date": gld_dates, "value": [28.0] * days}).write_csv(cache / "UUP.csv")
    output = tmp_path / "out"

    # Expected mask, computed by the SHIPPED builder on the staged inputs
    # (independent call — the implementation must call this same builder).
    src_dates, src_vals = mask_mod.read_dfii10_csv(cache / "DFII10.csv")
    expected = mask_mod.build_mask(
        gld_dates,
        gld_closes,
        src_dates,
        src_vals,
        z_thresh=-2.0,
        m_thresh=1.5,
        z_window=20,
        sma_window=10,
    )
    expected_days = frozenset(
        d for d, m in zip(expected["dates"], expected["mask"], strict=True) if m
    )
    assert 0 < len(expected_days) < days

    build_calls: list[dict] = []
    _real_build = mask_mod.build_mask

    def _recording_build(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        build_calls.append(dict(kwargs))
        return _real_build(*args, **kwargs)

    monkeypatch.setattr(mask_mod, "build_mask", _recording_build)

    resolve_calls: list[tuple[str, dict]] = []

    class _StubRiskModel:
        def __init__(self) -> None:
            from types import SimpleNamespace

            self.coefficients = SimpleNamespace(
                fit_start=start, fit_end=start + timedelta(days=days - 1), fit_rows=days
            )

        def rails(self, dates):  # type: ignore[no-untyped-def]
            n = len(dates)
            return pl.DataFrame({"low": [90.0] * n, "median": [100.0] * n, "high": [110.0] * n})

    def _fake_resolve(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
        resolve_calls.append((name, dict(kwargs)))
        return _StubRiskModel()

    monkeypatch.setattr(providers_mod, "resolve_sdca_risk_model", _fake_resolve)

    captured: dict[str, dict] = {}

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        captured[strategy] = dict(calibration or {})
        assert Path(captured[strategy]["risk_path"]).exists()
        ts = ohlcv["timestamp"].to_list()
        closes = ohlcv["close"].to_list()
        bars = [(str(t)[:10], float(c)) for t, c in zip(ts, closes, strict=True)]
        ohlc = [
            (str(t)[:10], float(c), float(c), float(c), float(c))
            for t, c in zip(ts, closes, strict=True)
        ]
        return _EmptyPositions(), bars, ohlc, {}, None

    monkeypatch.setattr(gts, "run_nautilus", _fake_nautilus)

    settings = copy.deepcopy(gts.load_settings())
    settings["strategies"]["gold_sdca"]["sdca"]["sell_mask"] = {
        "z_thresh": -2.0,
        "m_thresh": 1.5,
        "z_window": 20,
        "sma_window": 10,
    }
    gold_entry = gts.run_and_write(
        "gold_sdca", "GLD-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert gold_entry is not None

    # Mask built via the shipped builder at strict box values.
    assert len(build_calls) == 1
    assert build_calls[0]["z_thresh"] == -2.0
    assert build_calls[0]["m_thresh"] == 1.5
    # Sell dates reach the strategy overrides, equal to the builder's days.
    assert captured["gold_sdca"]["sell_dates"] == expected_days
    assert isinstance(captured["gold_sdca"]["sell_dates"], frozenset)
    # Window/z thread through to the selector at reselect defaults.
    gold_resolve = [kw for name, kw in resolve_calls if name == "rolling_z"]
    assert gold_resolve and gold_resolve[0].get("rolling_window") == 90
    assert gold_resolve[0].get("rolling_z") == 1.0
    # Provenance names the mask-day count.
    gold_payload = json.loads((output / "gold_sdca.json").read_text())
    assert f"{len(expected_days)} mask days" in " ".join(gold_payload["notes"])
    # Ruling 1 companion (LOW, #4804): the count labels its frame.
    assert "full delayed frame" in " ".join(gold_payload["notes"])

    # PAIRED BTC-None assert: identical outputs, no mask.
    btc_entry = gts.run_and_write(
        "btc_sdca", "BTC-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert btc_entry is not None
    assert "sell_dates" not in captured["btc_sdca"]
    assert set(captured["btc_sdca"]) == set(captured["gold_sdca"]) - {"sell_dates"}
    btc_payload = json.loads((output / "btc_sdca.json").read_text())
    assert "mask days" not in " ".join(btc_payload["notes"])


def _run_fail_closed_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, dfii10_body: str | None
) -> tuple[dict, dict, str, str]:
    """Shared stubbed harness for the Ruling-1 fail-closed tests (#4804).

    ``dfii10_body=None`` → DFII10.csv absent; otherwise that exact body is
    staged (a corrupt body proves the unreadable path). Runs gold (mask
    specified) + BTC (no mask) through ``run_and_write`` and returns
    ``(gold_calibration, btc_calibration, gold_notes, btc_notes)``.
    """
    import copy

    import digiquant.strategies.sdca.providers as providers_mod

    cache = tmp_path / "cache"
    cache.mkdir()
    start, days = date(2020, 1, 1), 60
    closes = [100.0] * days
    gld_dates = [start + timedelta(days=i) for i in range(days)]
    pl.DataFrame(
        {
            "timestamp": [d.isoformat() for d in gld_dates],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * days,
            "symbol": ["GLD-USD"] * days,
        }
    ).write_csv(cache / "GLD-USD.csv")
    _daily_ohlcv(start, days, close0=10_000.0, symbol="BTC-USD").write_csv(cache / "BTC-USD.csv")
    pl.DataFrame({"date": gld_dates, "value": [28.0] * days}).write_csv(cache / "UUP.csv")
    if dfii10_body is None:
        assert not (cache / "DFII10.csv").exists()
    else:
        (cache / "DFII10.csv").write_text(dfii10_body)
    output = tmp_path / "out"

    class _StubRiskModel:
        def __init__(self) -> None:
            from types import SimpleNamespace

            self.coefficients = SimpleNamespace(
                fit_start=start, fit_end=start + timedelta(days=days - 1), fit_rows=days
            )

        def rails(self, dates):  # type: ignore[no-untyped-def]
            n = len(dates)
            return pl.DataFrame({"low": [90.0] * n, "median": [100.0] * n, "high": [110.0] * n})

    def _fake_resolve(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
        return _StubRiskModel()

    monkeypatch.setattr(providers_mod, "resolve_sdca_risk_model", _fake_resolve)

    captured: dict[str, dict] = {}

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
        captured[strategy] = dict(calibration or {})
        assert Path(captured[strategy]["risk_path"]).exists()
        ts = ohlcv["timestamp"].to_list()
        closes_ = ohlcv["close"].to_list()
        bars = [(str(t)[:10], float(c)) for t, c in zip(ts, closes_, strict=True)]
        ohlc = [
            (str(t)[:10], float(c), float(c), float(c), float(c))
            for t, c in zip(ts, closes_, strict=True)
        ]
        return _EmptyPositions(), bars, ohlc, {}, None

    monkeypatch.setattr(gts, "run_nautilus", _fake_nautilus)

    settings = copy.deepcopy(gts.load_settings())
    settings["strategies"]["gold_sdca"]["sdca"]["sell_mask"] = {
        "z_thresh": -2.0,
        "m_thresh": 1.5,
        "z_window": 20,
        "sma_window": 10,
    }
    gold_entry = gts.run_and_write(
        "gold_sdca", "GLD-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert gold_entry is not None
    btc_entry = gts.run_and_write(
        "btc_sdca", "BTC-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert btc_entry is not None
    gold_notes = " ".join(json.loads((output / "gold_sdca.json").read_text())["notes"])
    btc_notes = " ".join(json.loads((output / "btc_sdca.json").read_text())["notes"])
    return captured["gold_sdca"], captured["btc_sdca"], gold_notes, btc_notes


def test_run_and_write_gold_sell_mask_missing_dfii10_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed mask, Ruling 1 (#4804): mask specified but DFII10 missing.

    ``sell_dates`` is the EMPTY set (sells blocked — premise-preserving for a
    long-biased system), never absent; provenance carries an explicit
    ``mask_unavailable`` flag, never silence. Paired BTC arm proves trigger
    exactness: no-mask entries keep None (no ``sell_dates`` key, no flag).
    """
    gold_cal, btc_cal, gold_notes, btc_notes = _run_fail_closed_case(
        tmp_path, monkeypatch, dfii10_body=None
    )
    assert gold_cal["sell_dates"] == frozenset()
    assert isinstance(gold_cal["sell_dates"], frozenset)
    assert "mask_unavailable" in gold_notes
    assert "sell_dates" not in btc_cal
    assert set(btc_cal) == set(gold_cal) - {"sell_dates"}
    assert "mask_unavailable" not in btc_notes


def test_run_and_write_gold_sell_mask_unreadable_dfii10_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed mask, Ruling 1 (#4804): mask specified but DFII10 corrupt.

    Same empty-set + flag contract as the missing-file case; paired BTC arm
    again proves the trigger never leaks onto no-mask entries.
    """
    gold_cal, btc_cal, gold_notes, btc_notes = _run_fail_closed_case(
        tmp_path,
        monkeypatch,
        # One valid row (so the extra-sources loader still parses) + one
        # corrupt date row (so the mask reader raises) — the unreadable path.
        dfii10_body="observation_date,DFII10\n2020-01-01,2.0\nnot-a-date,2.0\n",
    )
    assert gold_cal["sell_dates"] == frozenset()
    assert isinstance(gold_cal["sell_dates"], frozenset)
    assert "mask_unavailable" in gold_notes
    assert "sell_dates" not in btc_cal
    assert set(btc_cal) == set(gold_cal) - {"sell_dates"}
    assert "mask_unavailable" not in btc_notes


def test_run_and_write_rolling_z_provenance_records_window_z_without_coefficients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parameter-free provenance, Ruling 6 (#4804): REAL RollingZRiskModel through run_and_write.

    First real rolling model through the publish path (research built it via
    run_gold_curve_search; every unit pin stubs resolve). The gold arm builds
    a REAL RollingZRiskModel from the resolve kwargs — rails + index
    materialize for real — so provenance must record the window/z params
    instead of crashing on the fit-model assumption, and must NOT fabricate
    a Coefficients note. The paired BTC arm (fitted stub carrying
    .coefficients) proves fitted-model provenance is byte-unchanged.
    """
    from types import SimpleNamespace

    import digiquant.strategies.sdca.providers as providers_mod
    from digiquant.strategies.sdca.rolling_z import RollingZRiskModel

    cache = tmp_path / "cache"
    cache.mkdir()
    start, days = date(2020, 1, 1), 300
    _daily_ohlcv(start, days, close0=2500.0, symbol="GLD-USD").write_csv(cache / "GLD-USD.csv")
    _daily_ohlcv(start, days, close0=10_000.0, symbol="BTC-USD").write_csv(cache / "BTC-USD.csv")
    uup_dates = [start + timedelta(days=i) for i in range(days)]
    pl.DataFrame({"date": uup_dates, "value": [28.0 * (1.0005**i) for i in range(days)]}).write_csv(
        cache / "UUP.csv"
    )
    output = tmp_path / "out"

    class _StubFittedModel:
        """Fitted-model shape (btc_power_law / generic_valuation): carries .coefficients."""

        def __init__(self) -> None:
            self.coefficients = SimpleNamespace(
                fit_start=start, fit_end=start + timedelta(days=days - 1), fit_rows=days
            )

        def rails(self, dates):  # type: ignore[no-untyped-def]
            n = len(dates)
            return pl.DataFrame({"low": [90.0] * n, "median": [100.0] * n, "high": [110.0] * n})

    def _fake_resolve(name: str, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "rolling_z":
            return RollingZRiskModel(
                kwargs["dates"],
                kwargs["price"],
                window=int(kwargs["rolling_window"]),
                z=float(kwargs["rolling_z"]),
            )
        return _StubFittedModel()

    monkeypatch.setattr(providers_mod, "resolve_sdca_risk_model", _fake_resolve)

    class _EmptyPositions:
        def iterrows(self):
            return iter(())

    def _fake_nautilus(strategy, symbol, ohlcv, settings, calibration=None):
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

    settings = gts.load_settings()
    gold_entry = gts.run_and_write(
        "gold_sdca", "GLD-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert gold_entry is not None
    gold_notes = " ".join(json.loads((output / "gold_sdca.json").read_text())["notes"])
    assert "risk_model=rolling_z" in gold_notes
    assert "window=90" in gold_notes
    assert "z=1.0" in gold_notes
    assert "Coefficients" not in gold_notes

    # PAIRED fitted-path assert: BTC provenance byte-unchanged.
    btc_entry = gts.run_and_write(
        "btc_sdca", "BTC-USD", settings, cache, output, cal_source="file", signal_delay_days=0
    )
    assert btc_entry is not None
    btc_notes = " ".join(json.loads((output / "btc_sdca.json").read_text())["notes"])
    assert f"Coefficients {start} → {start + timedelta(days=days - 1)} ({days} rows)" in btc_notes
    assert "Preset btc_optimized" in btc_notes
