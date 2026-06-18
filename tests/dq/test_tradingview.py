"""Unit tests for digiquant.tradingview — Pine Script v5 export."""

from __future__ import annotations

from pathlib import Path

import pytest

from digiquant.tradingview import (
    _ALIAS_MAP,
    _PARAM_DEFAULTS,
    _PINE_TEMPLATES,
    _resolve,
    export_to_pine,
    import_from_pine,
)


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolve:
    def test_ema_alias(self) -> None:
        assert _resolve("ema") == "ema_cross"

    def test_bollinger_alias(self) -> None:
        assert _resolve("bollinger") == "bollinger_mr"

    def test_bb_mr_alias(self) -> None:
        assert _resolve("bb_mr") == "bollinger_mr"

    def test_rsi_alias(self) -> None:
        assert _resolve("rsi") == "rsi_momentum"

    def test_macd_alias(self) -> None:
        assert _resolve("macd") == "macd_trend"

    def test_ema_crossover_alias(self) -> None:
        assert _resolve("ema_crossover") == "ema_cross"

    def test_canonical_passthrough(self) -> None:
        assert _resolve("ema_cross") == "ema_cross"

    def test_case_insensitive(self) -> None:
        assert _resolve("EMA") == "ema_cross"
        assert _resolve("MACD") == "macd_trend"

    def test_unknown_passthrough(self) -> None:
        assert _resolve("no_such_strategy") == "no_such_strategy"


# ---------------------------------------------------------------------------
# Export — default params
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExportToPineDefaults:
    @pytest.mark.parametrize("strategy", list(_PINE_TEMPLATES.keys()))
    def test_export_succeeds_for_all_canonical_strategies(self, strategy: str) -> None:
        result = export_to_pine(strategy)
        assert result.success is True, f"Expected success for {strategy!r}: {result.message}"
        assert result.script is not None
        assert len(result.script) > 50

    @pytest.mark.parametrize("alias,canonical", list(_ALIAS_MAP.items()))
    def test_alias_resolves_to_same_result(self, alias: str, canonical: str) -> None:
        r_alias = export_to_pine(alias)
        r_canonical = export_to_pine(canonical)
        assert r_alias.success is True
        assert r_alias.script == r_canonical.script

    def test_unknown_strategy_returns_failure(self) -> None:
        result = export_to_pine("no_such_strategy_xyz")
        assert result.success is False
        assert "no_such_strategy_xyz" in result.message.lower() or "supported" in result.message.lower()

    def test_result_has_no_unresolved_template_vars(self) -> None:
        for strategy in _PINE_TEMPLATES:
            result = export_to_pine(strategy)
            assert "$" not in result.script, f"Unresolved $var in {strategy}: {result.script}"

    def test_pine_script_starts_with_version_header(self) -> None:
        result = export_to_pine("ema_cross")
        assert result.script.startswith("//@version=5")

    def test_artifact_path_is_none_without_output_path(self) -> None:
        result = export_to_pine("ema_cross")
        assert result.artifact_path is None


# ---------------------------------------------------------------------------
# Export — param overrides
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExportToPineParams:
    def test_ema_cross_fast_period_override(self) -> None:
        result = export_to_pine("ema_cross", params={"fast_period": 5, "slow_period": 50})
        assert "5" in result.script
        assert "50" in result.script

    def test_bollinger_period_override(self) -> None:
        result = export_to_pine("bollinger_mr", params={"bb_period": 15, "bb_std": 1.5, "sl_pct": 0.5})
        assert "15" in result.script
        assert "1.5" in result.script

    def test_rsi_param_override(self) -> None:
        result = export_to_pine("rsi_momentum", params={"rsi_period": 7, "oversold": 25.0, "overbought": 75.0})
        assert "7" in result.script

    def test_macd_param_override(self) -> None:
        result = export_to_pine("macd_trend", params={"fast_period": 8, "slow_period": 21, "signal_period": 5})
        assert "8" in result.script
        assert "21" in result.script
        assert "5" in result.script

    def test_partial_override_uses_defaults_for_missing(self) -> None:
        defaults = _PARAM_DEFAULTS["ema_cross"]
        result = export_to_pine("ema_cross", params={"fast_period": 3})
        # slow_period should still be default
        assert str(defaults["slow_period"]) in result.script

    def test_default_values_appear_in_script(self) -> None:
        for strategy, defaults in _PARAM_DEFAULTS.items():
            result = export_to_pine(strategy)
            for val in defaults.values():
                assert str(val) in result.script, f"Default {val} missing from {strategy} script"


# ---------------------------------------------------------------------------
# Export — file output
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExportToPineFileOutput:
    def test_writes_file_when_output_path_given(self, tmp_path: Path) -> None:
        out = tmp_path / "ema_cross.pine"
        result = export_to_pine("ema_cross", output_path=out)
        assert result.success is True
        assert out.exists()
        assert result.artifact_path == str(out)

    def test_file_content_matches_script(self, tmp_path: Path) -> None:
        out = tmp_path / "script.pine"
        result = export_to_pine("bollinger_mr", output_path=out)
        assert out.read_text(encoding="utf-8") == result.script

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        out = tmp_path / "deep" / "nested" / "dir" / "script.pine"
        result = export_to_pine("rsi_momentum", output_path=out)
        assert result.success is True
        assert out.exists()

    def test_script_returned_even_with_output_path(self, tmp_path: Path) -> None:
        out = tmp_path / "script.pine"
        result = export_to_pine("macd_trend", output_path=out)
        assert result.script is not None and len(result.script) > 0


# ---------------------------------------------------------------------------
# Import stub
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestImportFromPine:
    def test_always_returns_failure(self) -> None:
        r = import_from_pine("fake_path.pine")
        assert r.success is False

    def test_strategy_name_is_none(self) -> None:
        r = import_from_pine("whatever.pine")
        assert r.strategy_name is None

    def test_message_mentions_not_implemented(self) -> None:
        r = import_from_pine("anything.pine")
        assert "not implemented" in r.message.lower()
