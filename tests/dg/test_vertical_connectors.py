"""Hub HTTP connectors to DigiSearch / DigiQuant composite endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.connectors.digiquant import call_quant_workflow
from digigraph.connectors.digisearch import call_research_turn


@pytest.mark.unit
def test_call_research_turn_success() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"service": "digisearch", "total": 3})
    mock_client = MagicMock()
    mock_client.post = MagicMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_client)
    ctx.__exit__ = MagicMock(return_value=False)
    with patch("digigraph.connectors.digisearch.httpx.Client", return_value=ctx):
        out = call_research_turn(
            base_url="http://digisearch:8002",
            payload={"user_message": "alpha"},
            request_id="rid-1",
            bearer_token="tok",
        )
    assert out.get("ok") is True
    assert out.get("total") == 3
    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "http://digisearch:8002/v1/research_turn"


@pytest.mark.unit
def test_call_quant_workflow_http_error() -> None:
    import httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.json = MagicMock(return_value={"detail": "busy"})
    mock_resp.text = "busy"

    def _boom() -> None:
        raise httpx.HTTPStatusError("msg", request=MagicMock(), response=mock_resp)

    mock_resp.raise_for_status = _boom
    mock_client = MagicMock()
    mock_client.post = MagicMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_client)
    ctx.__exit__ = MagicMock(return_value=False)
    with patch("digigraph.connectors.digiquant.httpx.Client", return_value=ctx):
        out = call_quant_workflow(
            base_url="http://digiquant:8001",
            payload={"strategy_name": "x", "symbols": ["AAPL"]},
            request_id=None,
            bearer_token=None,
        )
    assert out.get("ok") is False
    assert out.get("status_code") == 503
