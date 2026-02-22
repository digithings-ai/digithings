"""Phase 1: Unit tests for graph nodes (research_node, backtest_node)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from digigraph.graph.nodes import backtest_node, research_node


@pytest.mark.unit
class TestResearchNode:
    """research_node: LLM success path and heuristic fallback."""

    def test_llm_valid_json_sets_strategy_and_symbols(self) -> None:
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = '{"strategy_name": "momentum_tech", "symbols": ["TSLA", "AMD"]}'
            out = research_node({"prompt": "momentum on tech"})
        assert out["strategy_name"] == "momentum_tech"
        assert out["symbols"] == ["TSLA", "AMD"]
        assert out["research_note"] == "LLM-extracted"

    def test_llm_json_with_markdown_block_stripped(self) -> None:
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = '```json\n{"strategy_name": "mean_reversion_stat_arb", "symbols": ["AAPL"]}\n```'
            out = research_node({"prompt": "stat arb"})
        assert out["strategy_name"] == "mean_reversion_stat_arb"
        assert out["symbols"] == ["AAPL"]
        assert out["research_note"] == "LLM-extracted"

    def test_llm_empty_content_keeps_defaults(self) -> None:
        """Empty LLM response does not update strategy/symbols; research_note stays empty."""
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = ""
            out = research_node({"prompt": "stat arb tech"})
        assert out["strategy_name"] == "mean_reversion_tech"
        assert out["research_note"] == ""

    def test_llm_invalid_json_uses_fallback(self) -> None:
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = "not json at all"
            out = research_node({"prompt": "tech"})
        assert out["strategy_name"] == "mean_reversion_tech"
        assert out["research_note"] == "heuristic-fallback"

    def test_llm_raises_uses_fallback(self) -> None:
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.side_effect = RuntimeError("API down")
            out = research_node({"prompt": "mean reversion on tech"})
        assert out["strategy_name"] == "mean_reversion"
        assert out["research_note"] == "heuristic-fallback"

    def test_empty_prompt_keeps_defaults(self) -> None:
        """Empty prompt with empty LLM response leaves defaults and research_note empty."""
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = ""
            out = research_node({"prompt": ""})
        assert out["strategy_name"] == "mean_reversion_tech"
        assert len(out["symbols"]) > 0
        assert out["research_note"] == ""

    def test_missing_prompt_key_treated_as_empty(self) -> None:
        """Missing prompt key is treated as empty string; no exception."""
        with patch("digigraph.graph.nodes.chat_completion") as m:
            m.return_value = ""
            out = research_node({})
        assert "strategy_name" in out
        assert "symbols" in out
        assert out["research_note"] == ""


@pytest.mark.unit
class TestBacktestNode:
    """backtest_node: DigiQuant success, timeout, 5xx, malformed response."""

    def test_success_returns_backtest_result(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "run_id": "bt-1",
            "status": "ok",
            "symbols": ["AAPL", "MSFT"],
        }
        mock_post = MagicMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            out = backtest_node({"strategy_name": "mr", "symbols": ["AAPL", "MSFT"]})
        assert out["backtest_result"] == {
            "run_id": "bt-1",
            "status": "ok",
            "symbols": ["AAPL", "MSFT"],
        }
        assert out["error"] is None
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["strategy_name"] == "mr"
        assert call_json["symbols"] == ["AAPL", "MSFT"]

    def test_uses_default_strategy_and_symbols_when_missing_in_state(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"run_id": "x", "status": "ok", "symbols": []}
        mock_client = MagicMock()
        mock_client.post = MagicMock(return_value=mock_response)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            out = backtest_node({})
        assert out["error"] is None
        call_json = mock_client.post.call_args[1]["json"]
        assert call_json["strategy_name"] == "mean_reversion_tech"
        assert call_json["symbols"] == ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]

    def test_http_error_sets_error_in_state(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock(status_code=500)
        )
        mock_client = MagicMock()
        mock_client.post = MagicMock(return_value=mock_response)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None
        assert "500" in out["error"]

    def test_timeout_sets_error_in_state(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None

    def test_connection_error_sets_error_in_state(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None
