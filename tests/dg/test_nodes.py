"""Phase 1: Unit tests for graph nodes (research_node, backtest_node)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from digigraph.graph.nodes import backtest_node, research_node


@pytest.mark.unit
class TestResearchNode:
    """research_node: LLM success path and error handling."""

    def test_llm_valid_json_sets_strategy_and_symbols(self) -> None:
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = '{"strategy_name": "momentum_tech", "symbols": ["TSLA", "AMD"]}'
                out = research_node({"prompt": "momentum on tech"})
        assert out["strategy_name"] == "momentum_tech"
        assert out["symbols"] == ["TSLA", "AMD"]
        assert out["research_note"] == "LLM-extracted"
        assert "error" not in out or out.get("error") is None

    def test_llm_json_with_markdown_block_stripped(self) -> None:
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = '```json\n{"strategy_name": "mean_reversion_stat_arb", "symbols": ["AAPL"]}\n```'
                out = research_node({"prompt": "stat arb"})
        assert out["strategy_name"] == "mean_reversion_stat_arb"
        assert out["symbols"] == ["AAPL"]
        assert out["research_note"] == "LLM-extracted"

    def test_llm_empty_content_returns_error(self) -> None:
        """Empty LLM response returns error; no defaults."""
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = ""
                out = research_node({"prompt": "stat arb tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert out.get("strategy_name") is None

    def test_llm_invalid_json_returns_error(self) -> None:
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = "not json at all"
                out = research_node({"prompt": "tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "invalid JSON" in out.get("error", "")


    def test_llm_raises_returns_error(self) -> None:
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.side_effect = RuntimeError("API down")
                out = research_node({"prompt": "mean reversion on tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "API down" in out.get("error", "")

    def test_empty_prompt_returns_error(self) -> None:
        """Empty prompt returns error; no defaults."""
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = ""
                out = research_node({"prompt": ""})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "prompt" in out.get("error", "").lower()

    def test_missing_prompt_key_returns_error(self) -> None:
        """Missing prompt key returns error."""
        with patch("digigraph.graph.nodes.digisearch", return_value=None):
            with patch("digigraph.graph.nodes.chat_completion") as m:
                m.return_value = ""
                out = research_node({})
        assert out["research_note"] == "error"
        assert out.get("error")

    def test_rag_stream_callback_called_for_tool_call_and_result(self) -> None:
        """When stream_callback is in state, RAG path calls it with tool_call and tool_result."""
        calls = []

        def stream_callback(event_type: str, data: dict) -> None:
            calls.append((event_type, data))

        with patch("digigraph.graph.nodes._digisearch_available", return_value=True):
            with patch("digigraph.graph.nodes._get_research_system_prompt", return_value="You have digisearch. Use it and summarize."):
                with patch("digigraph.graph.nodes.digisearch", return_value={
                    "results": [{"content": "Doc 1 content", "score": 0.9, "doc_id": "d1", "rank": 1, "metadata": {}}],
                    "total": 1,
                }):
                    with patch("digigraph.llm._stream_completion_one_turn") as m:
                        # RAG path uses streaming: first turn returns tool call, second returns final content
                        m.side_effect = [
                            ("", [{"id": "tc1", "function": {"name": "digisearch", "arguments": '{"query": "test query"}'}}]),
                            ("Summary of the docs.", None),
                        ]
                        out = research_node({"prompt": "find docs", "stream_callback": stream_callback})
        assert out.get("research_response") == "Summary of the docs."
        assert len(calls) >= 2
        assert calls[0][0] == "tool_call"
        assert calls[0][1].get("name") == "digisearch"
        assert calls[0][1].get("arguments", {}).get("query") == "test query"
        assert calls[1][0] == "tool_result"
        assert "Doc 1 content" in (calls[1][1].get("content") or "")


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
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
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

    def test_missing_strategy_and_symbols_returns_error(self) -> None:
        """Missing strategy_name/symbols returns error; no defaults."""
        out = backtest_node({})
        assert out["error"] is not None
        assert "required" in out["error"].lower()

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
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
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
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None

    def test_connection_error_sets_error_in_state(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None
