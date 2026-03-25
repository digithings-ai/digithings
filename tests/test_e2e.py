"""E2E tests: DigiGraph + DigiQuant stack (workflow, health, backtest, test_llm).

Run with stack up:
  docker compose up -d
  Export E2E_BEARER_TOKEN with a DigiKey-issued JWT (scopes must include digigraph:* / digiquant:* / digisearch:query).
  pytest -v -m e2e

Or local stack (no Docker port conflict):
  bash scripts/run_local.sh
  DIGIGRAPH_URL=http://127.0.0.1:18000 DIGIQUANT_URL=http://127.0.0.1:18001 E2E_BEARER_TOKEN=... pytest tests/test_e2e.py -v -m e2e
"""

from __future__ import annotations

import os
import time

import httpx
import pytest


def _e2e_bearer() -> str:
    tok = os.environ.get("E2E_BEARER_TOKEN", "").strip()
    if not tok:
        pytest.skip(
            "E2E_BEARER_TOKEN must be set to a DigiKey JWT for protected routes (see DIGIKEY.md /v1/oauth/token)."
        )
    return tok


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
def test_digisearch_health(digisearch_url: str, digisearch_available: bool) -> None:
    """DigiSearch /health returns 200. Skips if DigiSearch not in stack (e.g. run_local.sh)."""
    if not digisearch_available:
        pytest.skip("DigiSearch not available. Use docker compose up -d for full stack.")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digisearch_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digisearch"


@pytest.mark.e2e
def test_digisearch_query(digisearch_url: str, digisearch_available: bool) -> None:
    """DigiSearch POST /query returns results structure."""
    if not digisearch_available:
        pytest.skip("DigiSearch not available. Use docker compose up -d for full stack.")
    bearer = _e2e_bearer()
    with httpx.Client(
        timeout=5.0,
        headers={"Authorization": f"Bearer {bearer}"},
    ) as client:
        r = client.post(
            f"{digisearch_url}/query",
            json={"text": "mean reversion", "index_name": "default", "top_k": 5},
        )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "query" in data
    assert data["query"] == "mean reversion"
    assert isinstance(data["results"], list)


@pytest.mark.e2e
def test_digiquant_run_backtest_direct(
    digiquant_url: str,
    e2e_available: bool,
) -> None:
    """DigiQuant POST /run_backtest returns BacktestResult. Requires data_dir (e.g. /app/data in Docker)."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    data_dir = os.environ.get("E2E_DATA_DIR", "/app/data")
    bearer = _e2e_bearer()
    with httpx.Client(
        timeout=10.0,
        headers={"Authorization": f"Bearer {bearer}"},
    ) as client:
        r = client.post(
            f"{digiquant_url}/run_backtest",
            json={
                "strategy_name": "mean_reversion_stat_arb",
                "symbols": ["AAPL", "MSFT"],
                "data_dir": data_dir,
            },
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
    bearer = _e2e_bearer()
    start = time.monotonic()
    with httpx.Client(
        timeout=60.0,
        headers={"Authorization": f"Bearer {bearer}"},
    ) as client:
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
def test_litellm_proxy_liveliness(e2e_available: bool) -> None:
    """LiteLLM /health/liveliness or /health returns 200 when the default stack is up."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    base = os.environ.get("LITELLM_URL", "http://127.0.0.1:4000").rstrip("/")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{base}/health/liveliness")
        if r.status_code != 200:
            r = client.get(f"{base}/health")
    assert r.status_code == 200, r.text


@pytest.mark.e2e
def test_test_llm_endpoint(digigraph_url: str, e2e_available: bool) -> None:
    """GET /test_llm returns ok/model/reply or ok=false with error (same path as research node)."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    bearer = _e2e_bearer()
    with httpx.Client(
        timeout=30.0,
        headers={"Authorization": f"Bearer {bearer}"},
    ) as client:
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
