"""Baseline Pydantic v2 schema round-trip tests.

Each test instantiates a core model with valid data and verifies that
model_dump() returns a dict that can reconstruct an identical instance.
No external dependencies required.
"""

from __future__ import annotations

import pytest


@pytest.mark.baseline
def test_api_error_body_round_trip() -> None:
    """digibase.errors.ApiErrorBody — required fields only."""
    from digibase.errors import ApiErrorBody

    data = {"code": "http_404", "message": "Not found"}
    obj = ApiErrorBody(**data)
    dumped = obj.model_dump()
    assert dumped["code"] == "http_404"
    assert dumped["message"] == "Not found"
    assert dumped["request_id"] is None
    ApiErrorBody(**dumped)


@pytest.mark.baseline
def test_api_error_envelope_round_trip() -> None:
    """digibase.errors.ApiErrorEnvelope — nested model."""
    from digibase.errors import ApiErrorBody, ApiErrorEnvelope

    body = ApiErrorBody(code="validation_error", message="Bad input")
    envelope = ApiErrorEnvelope(error=body)
    dumped = envelope.model_dump()
    assert dumped["error"]["code"] == "validation_error"
    ApiErrorEnvelope(**dumped)


@pytest.mark.baseline
def test_token_claims_round_trip() -> None:
    """digikey.models.TokenClaims — JWT claim model."""
    from digikey.models import TokenClaims

    data = {
        "sub": "user-123",
        "iss": "http://127.0.0.1:8005",
        "aud": "digi-ecosystem",
        "scopes": ["read", "write"],
        "tenant_slug": "acme",
    }
    obj = TokenClaims(**data)
    dumped = obj.model_dump()
    assert dumped["sub"] == "user-123"
    assert dumped["scopes"] == ["read", "write"]
    TokenClaims(**dumped)


@pytest.mark.baseline
def test_smith_status_round_trip() -> None:
    """digismith.config.SmithStatus — observability status model."""
    from digismith.config import SmithStatus

    data = {
        "version": "0.1.0",
        "tracing_configured": False,
        "langsmith_sdk_installed": False,
    }
    obj = SmithStatus(**data)
    dumped = obj.model_dump()
    assert dumped["version"] == "0.1.0"
    assert dumped["tracing_configured"] is False
    SmithStatus(**dumped)


@pytest.mark.baseline
def test_backtest_result_round_trip() -> None:
    """digiquant.models.BacktestResult — quant backtest result model."""
    from digiquant.models import BacktestResult

    data = {
        "run_id": "bt-abc-001",
        "strategy_name": "ema_cross",
        "start_time": "2024-01-01T00:00:00",
        "end_time": "2024-12-31T23:59:59",
        "symbols": ["AAPL", "MSFT"],
        "total_pnl": 1250.75,
        "total_return_pct": 12.5,
        "num_trades": 42,
    }
    obj = BacktestResult(**data)
    dumped = obj.model_dump()
    assert dumped["run_id"] == "bt-abc-001"
    assert dumped["num_trades"] == 42
    BacktestResult(**dumped)
