"""Unit tests for digiquant.nautilus_runner — result parsers and helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from digiquant.nautilus_runner import _extract_pnl, _build_result


# ---------------------------------------------------------------------------
# _extract_pnl
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractPnl:
    def _report(self, **kwargs) -> pd.DataFrame:
        """Build a minimal account-report DataFrame."""
        return pd.DataFrame([kwargs])

    def test_none_report_returns_zeros(self) -> None:
        pnl, ret = _extract_pnl(None)
        assert pnl == 0.0
        assert ret == 0.0

    def test_empty_dataframe_returns_zeros(self) -> None:
        pnl, ret = _extract_pnl(pd.DataFrame())
        assert pnl == 0.0
        assert ret == 0.0

    def test_total_column_numeric(self) -> None:
        report = self._report(total=1_050_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(50_000.0)
        assert ret == pytest.approx(5.0)

    def test_balance_column_numeric(self) -> None:
        report = self._report(balance=900_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(-100_000.0)
        assert ret == pytest.approx(-10.0)

    def test_equity_column_numeric(self) -> None:
        report = self._report(equity=1_000_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(0.0)
        assert ret == pytest.approx(0.0)

    def test_total_column_string_with_currency(self) -> None:
        """Nautilus may return balance as '1100000.00 USD'."""
        report = self._report(total="1100000.00 USD")
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(100_000.0)
        assert ret == pytest.approx(10.0)

    def test_string_with_scientific_notation(self) -> None:
        report = self._report(total="1.05e6 USD")
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(50_000.0)

    def test_priority_total_over_balance(self) -> None:
        """'total' takes priority over 'balance'."""
        report = self._report(total=1_200_000.0, balance=800_000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(200_000.0)

    def test_no_recognised_column_returns_zeros(self) -> None:
        report = self._report(unrealised_pnl=5000.0)
        pnl, ret = _extract_pnl(report)
        assert pnl == 0.0
        assert ret == 0.0

    def test_multi_row_uses_last_row(self) -> None:
        """Account report may have multiple rows; last row is final balance."""
        report = pd.DataFrame([{"total": 900_000.0}, {"total": 1_100_000.0}])
        pnl, ret = _extract_pnl(report)
        assert pnl == pytest.approx(100_000.0)

    def test_malformed_string_returns_zeros(self) -> None:
        report = self._report(total="not-a-number")
        pnl, ret = _extract_pnl(report)
        assert pnl == 0.0
        assert ret == 0.0


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildResult:
    _BASE_NS = 1_700_000_000_000_000_000  # ~2023-11 in nanoseconds
    _END_NS = _BASE_NS + 86_400 * int(1e9)  # +1 day

    def _perf(self, sharpe=None, max_dd=None):
        return {
            "sharpe": sharpe,
            "max_dd": max_dd,
            "stats_returns": None,
            "stats_pnls": None,
            "stats_general": None,
            "returns_series": None,
            "realized_pnls_series": None,
        }

    def test_basic_fields(self) -> None:
        r = _build_result(
            run_id="test-abc",
            strategy_name="sma_cross",
            symbols_echo=["AAPL"],
            symbol="AAPL",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=5000.0,
            total_return_pct=0.5,
            num_trades=10,
            perf=self._perf(),
        )
        assert r.run_id == "test-abc"
        assert r.strategy_name == "sma_cross"
        assert r.symbols == ["AAPL"]
        assert r.num_trades == 10
        assert r.total_pnl == pytest.approx(5000.0)
        assert r.total_return_pct == pytest.approx(0.5)
        assert r.status == "ok"

    def test_timestamps_iso_format(self) -> None:
        r = _build_result(
            run_id="x",
            strategy_name="s",
            symbols_echo=[],
            symbol="BTC",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=0.0,
            total_return_pct=0.0,
            num_trades=0,
            perf=self._perf(),
        )
        assert r.start_time.endswith("Z")
        assert "T" in r.start_time
        assert r.end_time.endswith("Z")

    def test_perf_fields_propagated(self) -> None:
        r = _build_result(
            run_id="y",
            strategy_name="rsi",
            symbols_echo=["ETH"],
            symbol="ETH",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=1000.0,
            total_return_pct=0.1,
            num_trades=5,
            perf=self._perf(sharpe=1.5, max_dd=12.3),
        )
        assert r.sharpe_ratio == pytest.approx(1.5)
        assert r.max_drawdown_pct == pytest.approx(-12.3)

    def test_nan_pnl_becomes_zero(self) -> None:
        r = _build_result(
            run_id="z",
            strategy_name="s",
            symbols_echo=[],
            symbol="X",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=float("nan"),
            total_return_pct=float("nan"),
            num_trades=0,
            perf=self._perf(),
        )
        assert r.total_pnl == 0.0
        assert r.total_return_pct == 0.0

    def test_symbols_echo_empty_uses_symbol(self) -> None:
        r = _build_result(
            run_id="q",
            strategy_name="s",
            symbols_echo=[],
            symbol="MSFT",
            start_ts=self._BASE_NS,
            end_ts=self._END_NS,
            total_pnl=0.0,
            total_return_pct=0.0,
            num_trades=0,
            perf=self._perf(),
        )
        assert r.symbols == ["MSFT"]
