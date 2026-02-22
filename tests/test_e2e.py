"""E2E tests: DigiGraph + DigiQuant stack (workflow, health, backtest, test_llm).

Run with stack up:
  docker compose up -d
  pytest -v -m e2e

Or local stack (no Docker port conflict):
  bash scripts/run_local.sh
  DIGIGRAPH_URL=http://127.0.0.1:18000 DIGIQUANT_URL=http://127.0.0.1:18001 pytest tests/test_e2e.py -v -m e2e
"""

from __future__ import annotations

import time

import httpx
import pytest


@pytest.mark.e2e
def test_digiquant_health(digiquant_url: str, e2e_available: bool) -> None:
    """DigiQuant /health returns 200."""
    if not e2e_available:
        pytest.skip("E2E stack not available. Start with: docker compose up -d")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digiquant_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digiquant"


@pytest.mark.e2e
def test_digigraph_health(digigraph_url: str, e2e_available: bool) -> None:
    """DigiGraph /health returns 200."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digigraph_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digigraph"


@pytest.mark.e2e
def test_digiquant_run_backtest_direct(
    digiquant_url: str,
    e2e_available: bool,
) -> None:
    """DigiQuant POST /run_backtest returns BacktestResult."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    with httpx.Client(timeout=10.0) as client:
        r = client.post(
            f"{digiquant_url}/run_backtest",
            json={"strategy_name": "mean_reversion_stat_arb", "symbols": ["AAPL", "MSFT"]},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("run_id")
    assert data.get("status") == "ok"
    assert data.get("symbols") == ["AAPL", "MSFT"]


@pytest.mark.e2e
def test_workflow_returns_backtest(
    digigraph_url: str,
    e2e_available: bool,
) -> None:
    """Workflow: prompt → research → real Nautilus backtest result."""
    if not e2e_available:
        pytest.skip("E2E stack not available. Start with: docker compose up -d or bash scripts/run_local.sh (then set DIGIGRAPH_URL/DIGIQUANT_URL to 18000/18001)")
    start = time.monotonic()
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{digigraph_url}/workflow",
            json={"prompt": "Build me a mean-reversion stat-arb on tech", "session_id": "e2e"},
        )
    elapsed = time.monotonic() - start
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True, data
    assert "message" in data
    assert "backtest_result" in data
    bt = data["backtest_result"]
    assert bt is not None
    assert bt.get("status") == "ok"
    assert "strategy_name" in bt
    assert "symbols" in bt
    assert isinstance(bt["symbols"], list)
    assert len(bt["symbols"]) > 0
    # Real Nautilus backtest (no stub)
    run_id = bt.get("run_id") or ""
    assert run_id.startswith("nautilus-"), f"Expected real backtest run_id (nautilus-*), got {run_id!r}"
    assert elapsed < 60.0, f"Workflow took {elapsed:.1f}s"


@pytest.mark.e2e
def test_test_llm_endpoint(digigraph_url: str, e2e_available: bool) -> None:
    """GET /test_llm returns ok/model/reply or ok=false with error (same path as research node)."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{digigraph_url}/test_llm")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "ok" in data
    assert "model" in data
    assert "reply" in data
    if data.get("ok") is True:
        assert data.get("model")
    else:
        assert "error" in data
