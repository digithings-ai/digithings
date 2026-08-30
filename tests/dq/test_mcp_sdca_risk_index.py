"""MCP tool wiring for ``digiquant_build_sdca_risk_index`` (#3168)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

pytest.importorskip("mcp.server.fastmcp")

from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.history_cache import save_cached
from digiquant.mcp_server import create_mcp_server
from digiquant.strategies.sdca import btc_power_law as btc_power_law_mod

pytestmark = pytest.mark.unit

_EXAMPLE_COEFFICIENTS = (
    Path(btc_power_law_mod.__file__).parent / "btc_power_law_coefficients.example.json"
)


def _tool():
    server = create_mcp_server()
    return server._tool_manager.get_tool("digiquant_build_sdca_risk_index").fn


def _write_cache(cache_dir: Path, ticker: str = "BTC-USD", n: int = 10) -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    rows = {
        "timestamp": [start + timedelta(days=i) for i in range(n)],
        "open": [10_000.0] * n,
        "high": [10_100.0] * n,
        "low": [9_900.0] * n,
        "close": [10_000.0 + i * 10.0 for i in range(n)],
        "volume": [1.0] * n,
        "symbol": [ticker] * n,
    }
    save_cached(ticker, pl.DataFrame(rows).select(list(OHLCV_COLUMNS)), cache_dir)


class TestBuildSdcaRiskIndexTool:
    def test_registered(self) -> None:
        server = create_mcp_server()
        names = {t.name for t in server._tool_manager.list_tools()}
        assert "digiquant_build_sdca_risk_index" in names

    def test_missing_cache_returns_error_json(self, tmp_path: Path) -> None:
        payload = json.loads(
            _tool()(
                ticker="BTC-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                output_path=str(tmp_path / "risk.parquet"),
            )
        )
        assert "error" in payload
        assert "no cached price history" in payload["error"]

    def test_missing_coefficients_returns_error_json(self, tmp_path: Path) -> None:
        _write_cache(tmp_path)
        payload = json.loads(
            _tool()(
                ticker="BTC-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                coefficients_path=str(tmp_path / "missing.json"),
                output_path=str(tmp_path / "risk.parquet"),
            )
        )
        assert "error" in payload
        assert "not found" in payload["error"]

    def test_unknown_risk_model_returns_error_json(self, tmp_path: Path) -> None:
        payload = json.loads(
            _tool()(
                ticker="BTC-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                risk_model="not_a_provider",
            )
        )
        assert payload == {"error": "unknown risk_model 'not_a_provider'"}

    def test_builds_parquet_from_cached_history(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, n=15)
        out = tmp_path / "risk.parquet"
        payload = json.loads(
            _tool()(
                ticker="BTC-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                coefficients_path=str(_EXAMPLE_COEFFICIENTS),
                output_path=str(out),
            )
        )
        assert "error" not in payload
        assert payload["row_count"] == 15
        assert payload["date_start"] == "2020-01-01"
        assert payload["date_end"] == "2020-01-15"
        assert payload["null_risk_days"] == 0
        assert Path(payload["path"]).exists()
        loaded = pl.read_parquet(out)
        assert loaded.columns == ["date", "risk"]
        assert loaded.height == 15
        assert loaded["date"].dtype == pl.Date
        assert loaded["date"][0] == date(2020, 1, 1)

    def test_rolling_z_builds_parquet_from_short_cache(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, ticker="SOL-USD", n=40)
        out = tmp_path / "sol_risk.parquet"
        payload = json.loads(
            _tool()(
                ticker="SOL-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                risk_model="rolling_z",
                rolling_window=10,
                output_path=str(out),
            )
        )
        assert "error" not in payload, payload
        assert payload["row_count"] == 40
        assert payload["null_risk_days"] >= 1
        assert Path(payload["path"]).exists()

    def test_generic_valuation_builds_parquet_from_eth_like_cache(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, ticker="ETH-USD", n=900)
        out = tmp_path / "eth_risk.parquet"
        payload = json.loads(
            _tool()(
                ticker="ETH-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                risk_model="generic_valuation",
                valuation_form="log_linear",
                output_path=str(out),
            )
        )
        assert "error" not in payload, payload
        assert payload["row_count"] == 900
        assert payload["null_risk_days"] == 0
        loaded = pl.read_parquet(out)
        assert loaded.columns == ["date", "risk"]
        assert loaded["risk"].null_count() == 0
