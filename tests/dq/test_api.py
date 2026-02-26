"""API tests for DigiQuant FastAPI app (integration with TestClient)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from digiquant.data.loader import generate_synthetic_ohlcv
from digiquant.server import app

SAMPLE_BACKTEST_PAYLOAD = {
    "strategy_name": "mean_reversion_tech",
    "symbols": ["AAPL", "MSFT", "GOOGL"],
}


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
    return TestClient(app)


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
        assert data["run_id"].startswith("nautilus-")

    def test_returns_503_when_nautilus_unavailable(
        self, client: TestClient, data_dir: Path
    ) -> None:
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
            payload = {**SAMPLE_BACKTEST_PAYLOAD, "data_dir": str(data_dir)}
            r = client.post("/run_backtest", json=payload)
            assert r.status_code == 503
            assert "nautilus" in r.json().get("detail", "").lower()

    def test_returns_400_when_no_data_provided(self, client: TestClient) -> None:
        r = client.post("/run_backtest", json=SAMPLE_BACKTEST_PAYLOAD)
        assert r.status_code == 400
        assert "data_path" in r.json().get("detail", "").lower() or "data_dir" in r.json().get("detail", "").lower()

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
        assert "not implemented" in data.get("message", "").lower()


@pytest.mark.unit
class TestRunOptimize:
    """POST /run_optimize. Requires data_path or data_dir."""

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
        with patch("digiquant.backtest.run_nautilus_backtest", return_value=None):
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
        assert "Unsupported target" in r.json()["detail"]


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
