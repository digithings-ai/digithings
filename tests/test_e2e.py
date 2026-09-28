"""E2E tests: digigraph + digiquant stack (workflow, health, backtest, test_llm).

Run with stack up:
  docker compose up -d
  Export E2E_BEARER_TOKEN with a digikey-issued JWT (scopes must include digigraph:* / digiquant:* / digisearch:query).
  pytest -v -m e2e

Or local stack (no Docker port conflict):
  bash scripts/run_local.sh
  DIGIGRAPH_URL=http://127.0.0.1:18000 DIGIQUANT_URL=http://127.0.0.1:18001 E2E_BEARER_TOKEN=... pytest tests/test_e2e.py -v -m e2e
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import httpx
import pytest

# The two symbols test_digiquant_run_backtest_direct asks for. Both must have a
# `{symbol}.csv` or the multi-symbol backtest returns None -> RuntimeError -> 503.
_DIRECT_BACKTEST_SYMBOLS = ("AAPL", "MSFT")
_DATA_README = "digiquant/data/README.md"


def _e2e_bearer() -> str:
    tok = os.environ.get("E2E_BEARER_TOKEN", "").strip()
    if not tok:
        pytest.skip(
            "E2E_BEARER_TOKEN must be set to a digikey JWT for protected routes (see digikey/ARCHITECTURE.md /v1/oauth/token)."
        )
    return tok


def _ohlcv_data_dirs(data_dir: str) -> list[Path]:
    """Directories on the *test host* that may hold `{symbol}.csv` OHLCV files.

    Compose mounts ``./digiquant/data`` read-only at ``/app/data`` inside the
    digiquant container, but the pytest client runs on the host/runner where
    ``/app/data`` does not exist. The mount source is also checked so a developer
    with real CSVs under ``digiquant/data`` gets a real run instead of a false
    skip; CI (no CSVs — ``.gitignore`` excludes ``**/data/*.csv``) skips.
    """
    candidates = [Path(data_dir)]
    mount_source = Path(__file__).resolve().parents[1] / "digiquant" / "data"
    if mount_source not in candidates:
        candidates.append(mount_source)
    return candidates


def _ohlcv_symbols(data_dir: str) -> set[str]:
    """Stems of every ``*.csv`` visible in a candidate OHLCV directory."""
    found: set[str] = set()
    for directory in _ohlcv_data_dirs(data_dir):
        if directory.is_dir():
            found.update(path.stem for path in directory.glob("*.csv"))
    return found


def _skip_if_no_ohlcv(data_dir: str, symbols: tuple[str, ...] | None = None) -> None:
    """Skip when the backtest has no OHLCV CSVs to read.

    Without the CSVs the API fails closed with a 503 (``RuntimeError`` in
    digiquant/server.py) rather than returning a backtest, so this is a missing
    fixture, not a product regression. ``symbols=None`` means any CSV is enough
    (the workflow research node picks its own basket).
    """
    present = _ohlcv_symbols(data_dir)
    if symbols is None:
        if not present:
            pytest.skip(
                f"No OHLCV CSVs in {data_dir} (or the compose mount source digiquant/data): "
                f"the backtest cannot run in CI. See {_DATA_README} to fetch/author sample data."
            )
        return
    missing = [sym for sym in symbols if sym not in present]
    if missing:
        pytest.skip(
            f"No OHLCV CSV for {', '.join(missing)} in {data_dir} (or the compose mount "
            f"source digiquant/data): the multi-symbol backtest would 503. See {_DATA_README}."
        )


@pytest.mark.e2e
def test_digiquant_health(digiquant_url: str, e2e_available: bool) -> None:
    """digiquant /health returns 200."""
    if not e2e_available:
        pytest.skip("E2E stack not available. Start with: docker compose up -d")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digiquant_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digiquant"


@pytest.mark.e2e
def test_digigraph_health(digigraph_url: str, e2e_available: bool) -> None:
    """digigraph /health returns 200."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digigraph_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digigraph"


@pytest.mark.e2e
def test_digisearch_health(digisearch_url: str, digisearch_available: bool) -> None:
    """digisearch /health returns 200. Skips if digisearch not in stack (e.g. run_local.sh)."""
    if not digisearch_available:
        pytest.skip("digisearch not available. Use docker compose up -d for full stack.")
    with httpx.Client(timeout=5.0) as client:
        r = client.get(f"{digisearch_url}/health")
    assert r.status_code == 200
    assert r.json().get("service") == "digisearch"


@pytest.mark.e2e
def test_digisearch_query(digisearch_url: str, digisearch_available: bool) -> None:
    """digisearch POST /query returns results structure."""
    if not digisearch_available:
        pytest.skip("digisearch not available. Use docker compose up -d for full stack.")
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
    """digiquant POST /run_backtest returns BacktestResult. Requires data_dir (e.g. /app/data in Docker)."""
    if not e2e_available:
        pytest.skip("E2E stack not available")
    data_dir = os.environ.get("E2E_DATA_DIR", "/app/data")
    _skip_if_no_ohlcv(data_dir, _DIRECT_BACKTEST_SYMBOLS)
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
    # The workflow's backtest node needs real OHLCV CSVs (digigraph sets
    # DIGIQUANT_DATA_DIR=/app/data, backed by the ./digiquant/data mount). With
    # no CSVs it returns an error rather than a backtest, so skip rather than
    # fail — same missing-fixture reason as the direct run_backtest test.
    _skip_if_no_ohlcv(os.environ.get("E2E_DATA_DIR", "/app/data"))
    bearer = _e2e_bearer()
    start = time.monotonic()
    # Bounded above the workflow's own budgets: 120 s /v1/jobs polling and a
    # 90 s SSE progress stream (digigraph/graph/nodes.py), so 180 s covers the
    # slowest path without masking a genuine hang.
    with httpx.Client(
        timeout=180.0,
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
    # Real Nautilus backtest (no stub). A single-symbol run is `nautilus-<hex>`;
    # a multi-symbol aggregate is `multi-<hex>` (nautilus_runner.py:597), which is
    # what the research node's basket produces — accept both real contracts.
    run_id = bt.get("run_id") or ""
    assert re.fullmatch(r"(?:nautilus|multi)-[0-9a-f]{8}", run_id), (
        f"Expected real backtest run_id (nautilus-*/multi-*), got {run_id!r}"
    )
    assert elapsed < 180.0, f"Workflow took {elapsed:.1f}s"


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
