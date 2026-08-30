"""MCP + orchestrator wiring for SDCA platform tools (Bitview, Stage A)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — fake HTTP session

import polars as pl
import pytest
from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.history_cache import save_cached
from digiquant.orchestrator_tools import build_orchestrator_tool_manifest
from digiquant.sdca_mcp import run_fetch_bitview_series, run_fit_sdca_weights
from digiquant.strategies.sdca.asset_profile import SdcaAssetProfile
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec

pytest.importorskip("mcp.server.fastmcp")

from digiquant.mcp_server import create_mcp_server

pytestmark = pytest.mark.unit

_PLATFORM = {
    "digiquant_fetch_bitview_series",
    "digiquant_fit_sdca_weights",
    "digiquant_build_sdca_risk_index",
    "digiquant_run_optimize",
    "digiquant_fit_btc_power_law",
    "digiquant_fetch_coinbase_ohlcv",
}


def _tool_names() -> set[str]:
    server = create_mcp_server()
    return {t.name for t in server._tool_manager.list_tools()}


def _mcp(name: str):
    return create_mcp_server()._tool_manager.get_tool(name).fn


def _mvrv_slice() -> dict[str, Any]:
    return {
        "version": 1,
        "index": "day1",
        "type": "StoredF32",
        "start": 800,
        "end": 805,
        "stamp": "2026-08-30T22:07:42Z",
        "data": [3.21, 3.21, 3.18, 3.14, 2.93],
    }


class _FakeResp:
    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


class _FakeSession:
    def __init__(self, body: object) -> None:
        self._body = body
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs: Any) -> _FakeResp:
        self.calls.append(url)
        return _FakeResp(self._body)


def _ohlcv(ticker: str, n: int, start: date) -> pl.DataFrame:
    ts = [
        datetime(start.year, start.month, start.day, tzinfo=UTC) + timedelta(days=i)
        for i in range(n)
    ]
    close = [100.0 + 0.2 * i for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": ts,
            "open": close,
            "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close],
            "close": close,
            "volume": [1.0] * n,
            "symbol": [ticker] * n,
        }
    ).select(list(OHLCV_COLUMNS))


def _profile() -> SdcaAssetProfile:
    start = date(2020, 1, 1)
    return SdcaAssetProfile(
        symbol="ETH-USD",
        risk_model="rolling_z",
        oscillators=SdcaOscillatorSpec(sma_band_window=20, sma_band_min_samples=10),
        cycle_windows=SdcaCycleWindows(
            windows=(
                CycleWindow(
                    name="t",
                    kind=CycleKind.TROUGH,
                    start=start,
                    end=date(2020, 1, 25),
                ),
                CycleWindow(
                    name="p",
                    kind=CycleKind.PEAK,
                    start=date(2020, 3, 1),
                    end=date(2020, 3, 25),
                ),
            )
        ),
        extra_indicators=("weekly_rsi", "weekly_macd", "sma_band"),
    )


class TestPlatformToolRegistration:
    def test_mcp_and_orchestrator_share_sdca_tools(self) -> None:
        mcp = _tool_names()
        missing_mcp = _PLATFORM - mcp
        assert not missing_mcp, f"missing MCP tools: {sorted(missing_mcp)}"
        manifest = {row["function"]["name"] for row in build_orchestrator_tool_manifest()}
        missing_orch = _PLATFORM - manifest
        assert not missing_orch, f"missing orchestrator tools: {sorted(missing_orch)}"


class TestFetchBitviewMcp:
    def test_mocked_http_writes_parquet(self, tmp_path: Path) -> None:
        session = _FakeSession(
            [
                _mvrv_slice(),
                {**_mvrv_slice(), "data": [1.0] * 5},
                {**_mvrv_slice(), "data": [0.5] * 5},
                {**_mvrv_slice(), "data": [0.2] * 5},
            ]
        )
        payload = json.loads(
            run_fetch_bitview_series(
                series_ids_json='["mvrv","asopr_24h","puell_multiple","rhodl_ratio"]',
                cache_dir=str(tmp_path),
                session=session,
            )
        )
        assert "error" not in payload or payload.get("series")
        assert payload["series"]["mvrv"]["row_count"] == 5
        assert Path(payload["series"]["mvrv"]["path"]).exists()

    def test_nupl_error_json(self) -> None:
        payload = json.loads(
            run_fetch_bitview_series(series_ids_json='["nupl"]', session=_FakeSession([]))
        )
        assert "dual-count" in payload["series"]["nupl"]["error"]

    def test_mcp_tool_registered_fail_soft(self) -> None:
        raw = _mcp("digiquant_fetch_bitview_series")(series_ids_json="not-json")
        payload = json.loads(raw)
        assert "error" in payload


class TestFitSdcaWeightsMcp:
    def test_missing_cache_error_json(self, tmp_path: Path) -> None:
        payload = json.loads(
            run_fit_sdca_weights(profile="eth_research_v1", cache_dir=str(tmp_path))
        )
        assert "error" in payload
        assert "no cached price history" in payload["error"]

    def test_profile_json_fits(self, tmp_path: Path) -> None:
        save_cached("ETH-USD", _ohlcv("ETH-USD", 90, date(2020, 1, 1)), tmp_path)
        payload = json.loads(
            run_fit_sdca_weights(
                profile="custom",
                profile_json=_profile().model_dump_json(),
                cache_dir=str(tmp_path),
                rolling_window=10,
                output_path=str(tmp_path / "w.json"),
            )
        )
        assert "error" not in payload
        assert payload["symbol"] == "ETH-USD"
        assert "regularized_weights" in payload
        assert "weekly_rsi_weight" in payload["regularized_weight_params"]
        assert abs(sum(payload["regularized_weights"].values()) - 1.0) < 1e-6

    def test_mcp_unknown_profile_error_json(self) -> None:
        payload = json.loads(_mcp("digiquant_fit_sdca_weights")(profile="nope"))
        assert "error" in payload


class TestBuildRiskIndexProfile:
    def test_profile_json_uses_rolling_z(self, tmp_path: Path) -> None:
        save_cached("ETH-USD", _ohlcv("ETH-USD", 40, date(2020, 1, 1)), tmp_path)
        payload = json.loads(
            _mcp("digiquant_build_sdca_risk_index")(
                ticker="ETH-USD",
                cache_dir=str(tmp_path),
                refresh=False,
                profile_json=_profile().model_dump_json(),
                output_path=str(tmp_path / "risk.parquet"),
                rolling_window=10,
            )
        )
        assert "error" not in payload
        assert payload["row_count"] == 40
        assert Path(payload["path"]).exists()
