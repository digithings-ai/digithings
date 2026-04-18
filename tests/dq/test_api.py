"""API tests for DigiQuant FastAPI app (integration with TestClient)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digiquant.data.loader import generate_synthetic_ohlcv
from digiquant.models import BacktestResult
from digiquant.server import app
from tests.digi_test_jwt import auth_headers

# SIGABRT on Linux CI when Nautilus engine runs under pytest+uvloop. See #42.
_SKIP_NATIVE_CRASH = pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Native crash (exit 134) under Linux CI — tracked in #42",
)

SAMPLE_BACKTEST_PAYLOAD = {
    "strategy_name": "mean_reversion_tech",
    "symbols": ["AAPL", "MSFT", "GOOGL"],
}


def _api_error_message(data: dict) -> str:
    err = data.get("error")
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    return str(data.get("detail", ""))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Create temp dir with AAPL, MSFT, GOOGL OHLCV CSVs."""
    for sym in ["AAPL", "MSFT", "GOOGL"]:
        generate_synthetic_ohlcv([sym], freq="1d").write_csv(tmp_path / f"{sym}.csv")
    return tmp_path
SAMPLE_BACKTEST_RESULT_FIELDS = [
    "run_id", "strategy_name", "symbols", "start_time", "end_time",
    "total_pnl", "total_return_pct", "sharpe_ratio", "max_drawdown_pct",
    "num_trades", "status", "message",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.mark.unit
class TestListStrategies:
    """GET /strategies."""

    def test_returns_list(self, client: TestClient) -> None:
        r = client.get("/strategies")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(item.get("name") == "ema_cross" for item in data)


@pytest.mark.unit
class TestHealth:
    """GET /health."""

    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200

    def test_returns_json_with_status(self, client: TestClient) -> None:
        r = client.get("/health")
        data = r.json()
        assert data.get("status") == "ok"
        assert data.get("service") == "digiquant"


@pytest.mark.unit
class TestRunBacktest:
    """POST /run_backtest. Requires data_path or data_dir (or DIGIQUANT_DATA_DIR)."""

    @_SKIP_NATIVE_CRASH
    def test_returns_200_with_valid_body_when_nautilus_available(
        self, client: TestClient, data_dir: Path
    ) -> None:
        pytest.importorskip("nautilus_trader")
        payload = {**SAMPLE_BACKTEST_PAYLOAD, "data_dir": str(data_dir)}
        r = client.post("/run_backtest", json=payload)
        assert r.status_code == 200
        data = r.json()
        for field in SAMPLE_BACKTEST_RESULT_FIELDS:
            assert field in data, f"Missing field: {field}"
        assert data["status"] == "ok"
        assert data["symbols"] == SAMPLE_BACKTEST_PAYLOAD["symbols"]
        # Multi-symbol runs use "multi-" prefix; single-symbol uses "nautilus-".
        assert data["run_id"].startswith(("nautilus-", "multi-"))

    def test_returns_503_when_nautilus_unavailable(
        self, client: TestClient, data_dir: Path
    ) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            payload = {**SAMPLE_BACKTEST_PAYLOAD, "data_dir": str(data_dir)}
            r = client.post("/run_backtest", json=payload)
            assert r.status_code == 503
            assert "nautilus" in _api_error_message(r.json()).lower()

    def test_returns_400_when_no_data_provided(self, client: TestClient) -> None:
        r = client.post("/run_backtest", json=SAMPLE_BACKTEST_PAYLOAD)
        assert r.status_code == 400
        msg = _api_error_message(r.json()).lower()
        assert "data_path" in msg or "data_dir" in msg

    def test_rejects_missing_required_fields(self, client: TestClient, data_dir: Path) -> None:
        """Missing strategy_name or symbols returns 422."""
        r = client.post("/run_backtest", json={"data_dir": str(data_dir)})
        assert r.status_code == 422

    def test_validation_rejects_invalid_types(self, client: TestClient, data_dir: Path) -> None:
        r = client.post(
            "/run_backtest",
            json={"strategy_name": 123, "symbols": "not-a-list", "data_dir": str(data_dir)},
        )
        assert r.status_code == 422

    def test_strategy_params_forwarded_to_run_backtest(
        self, client: TestClient, data_dir: Path
    ) -> None:
        fake = BacktestResult(
            run_id="t-1",
            strategy_name="ema_cross",
            symbols=["AAPL"],
            start_time="2020-01-01T00:00:00",
            end_time="2020-06-01T00:00:00",
            total_pnl=0.0,
            total_return_pct=0.0,
            sharpe_ratio=None,
            max_drawdown_pct=None,
            num_trades=0,
            status="ok",
            message="",
        )
        with patch("digiquant.server.service_run_backtest", return_value=fake) as m_run:
            r = client.post(
                "/run_backtest",
                json={
                    "strategy_name": "ema_cross",
                    "symbols": ["AAPL"],
                    "data_dir": str(data_dir),
                    "strategy_params": {"fast_ema_period": 12, "slow_ema_period": 28},
                },
            )
            assert r.status_code == 200
            call_kw = m_run.call_args.kwargs
            assert call_kw["strategy_params"] == {"fast_ema_period": 12, "slow_ema_period": 28}


@pytest.mark.unit
class TestCheckDrift:
    """GET /check_drift (Phase 3)."""

    def test_returns_200_and_addm_result(self, client: TestClient) -> None:
        r = client.get("/check_drift?strategy_id=mean_reversion_tech")
        assert r.status_code == 200
        data = r.json()
        assert "drift_detected" in data
        assert data["drift_detected"] is False
        assert data.get("implemented") is False
        # Message describes insufficient history when no observations have been recorded.
        assert data.get("message", "") != ""


@pytest.mark.unit
class TestRunOptimize:
    """POST /run_optimize. Requires data_path or data_dir."""

    @_SKIP_NATIVE_CRASH
    def test_returns_200_with_valid_body_when_nautilus_available(
        self, client: TestClient, data_dir: Path
    ) -> None:
        pytest.importorskip("nautilus_trader")
        r = client.post(
            "/run_optimize",
            json={"strategy_name": "ema_cross", "symbols": ["AAPL"], "data_dir": str(data_dir)},
        )
        assert r.status_code == 200
        data = r.json()
        assert "run_id" in data and data["run_id"].startswith("optimize-")
        assert data["strategy_name"] == "ema_cross"
        assert data["num_evaluations"] >= 1
        assert data["status"] == "ok"

    def test_returns_503_when_nautilus_unavailable(
        self, client: TestClient, data_dir: Path
    ) -> None:
        # Patch run_backtest + force single worker so the patch applies (ProcessPool workers
        # spawn new processes and don't inherit unittest.mock patches).
        with patch("digiquant.optimize.run_backtest", side_effect=RuntimeError("nautilus not installed")), \
             patch("digiquant.optimize._DEFAULT_WORKERS", 1):
            r = client.post(
                "/run_optimize",
                json={"strategy_name": "ema_cross", "symbols": ["AAPL"], "data_dir": str(data_dir)},
            )
            assert r.status_code == 503

    def test_rejects_missing_required_fields(self, client: TestClient, data_dir: Path) -> None:
        """Missing strategy_name or symbols returns 422."""
        r = client.post("/run_optimize", json={"data_dir": str(data_dir)})
        assert r.status_code == 422


@pytest.mark.unit
class TestRunExport:
    """POST /run_export."""

    def test_returns_200_with_valid_body(self, client: TestClient) -> None:
        r = client.post(
            "/run_export",
            json={"strategy_name": "mean_reversion_tech", "target": "nautilus"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["target"] == "nautilus"
        assert data["strategy_name"] == "mean_reversion_tech"
        assert data["status"] == "ok"

    def test_rejects_unsupported_target(self, client: TestClient) -> None:
        r = client.post(
            "/run_export",
            json={"strategy_name": "x", "target": "unknown_broker"},
        )
        assert r.status_code == 400
        assert "Unsupported target" in _api_error_message(r.json())

    def test_nautilus_bundle_writes_zip(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXPORT_OUTPUT_DIR", str(tmp_path))
        r = client.post(
            "/run_export",
            json={
                "strategy_name": "ema_cross",
                "target": "nautilus_bundle",
                "params": {"fast_ema_period": 10, "slow_ema_period": 20},
            },
        )
        assert r.status_code == 200
        data = r.json()
        path = Path(data["artifact_path"])
        assert path.suffix == ".zip"
        assert path.exists()


@pytest.mark.unit
class TestRunPipeline:
    """POST /run_pipeline. Requires data_path or data_dir."""

    def test_returns_200_with_backtest_optimize_export_when_nautilus_available(
        self, client: TestClient, data_dir: Path
    ) -> None:
        pytest.importorskip("nautilus_trader")
        r = client.post(
            "/run_pipeline",
            json={
                "strategy_name": "ema_cross",
                "symbols": ["AAPL", "MSFT"],
                "data_dir": str(data_dir),
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "backtest" in data and "optimize" in data and "export" in data
        assert data["backtest"]["status"] == "ok"
        assert data["optimize"]["status"] == "ok"
        assert data["export"]["status"] == "ok"

    def test_returns_503_when_nautilus_unavailable(
        self, client: TestClient, data_dir: Path
    ) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            r = client.post(
                "/run_pipeline",
                json={"strategy_name": "ema_cross", "symbols": ["AAPL"], "data_dir": str(data_dir)},
            )
            assert r.status_code == 503


@pytest.mark.unit
class TestV1Workflow:
    """POST /v1/workflow returns trace + step payloads."""

    def test_returns_trace_when_pipeline_mocks(self, client: TestClient, data_dir: Path) -> None:
        fake = {
            "error": None,
            "trace": [{"step": "validate", "status": "ok"}, {"step": "backtest", "status": "ok"}],
            "backtest": {
                "run_id": "b1",
                "strategy_name": "ema_cross",
                "symbols": ["AAPL"],
                "start_time": "2020-01-01",
                "end_time": "2020-02-01",
                "status": "ok",
            },
        }
        with patch("digiquant.server.run_quant_workflow", return_value=fake):
            r = client.post(
                "/v1/workflow",
                json={"strategy_name": "ema_cross", "symbols": ["AAPL"], "data_dir": str(data_dir)},
            )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("trace")
        assert data.get("backtest", {}).get("run_id") == "b1"
