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

    def test_default_weights_match_valuation_only_risk(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, n=15)
        out_default = tmp_path / "risk_default.parquet"
        out_explicit = tmp_path / "risk_explicit.parquet"
        base = dict(
            ticker="BTC-USD",
            cache_dir=str(tmp_path),
            refresh=False,
            coefficients_path=str(_EXAMPLE_COEFFICIENTS),
        )
        a = json.loads(_tool()(**base, output_path=str(out_default)))
        b = json.loads(
            _tool()(
                **base,
                output_path=str(out_explicit),
                indicator_weights='{"valuation": 1.0, "m2": 0.0, "rs_eth": 0.0, "dxy": 0.0}',
            )
        )
        assert "error" not in a and "error" not in b
        default_risk = pl.read_parquet(out_default)["risk"].to_list()
        explicit_risk = pl.read_parquet(out_explicit)["risk"].to_list()
        assert default_risk == pytest.approx(explicit_risk)

    def test_m2_weight_changes_risk_when_series_present(self, tmp_path: Path) -> None:
        _write_cache(tmp_path, n=80)
        m2_path = tmp_path / "M2SL.csv"
        start = date(2020, 1, 1)
        rows = ["date,value"]
        for i in range(80):
            d = start + timedelta(days=i)
            rows.append(f"{d},{100.0 + i}")
        m2_path.write_text("\n".join(rows) + "\n")
        out_solo = tmp_path / "solo.parquet"
        out_blend = tmp_path / "blend.parquet"
        base = dict(
            ticker="BTC-USD",
            cache_dir=str(tmp_path),
            refresh=False,
            coefficients_path=str(_EXAMPLE_COEFFICIENTS),
        )
        json.loads(_tool()(**base, output_path=str(out_solo)))
        payload = json.loads(
            _tool()(
                **base,
                output_path=str(out_blend),
                indicator_weights='{"valuation": 1.0, "m2": 1.0}',
                m2_path=str(m2_path),
            )
        )
        assert "error" not in payload
        solo = pl.read_parquet(out_solo)["risk"]
        blend = pl.read_parquet(out_blend)["risk"]
        assert solo.to_list() != blend.to_list()
