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
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = '{"strategy_name": "momentum_tech", "symbols": ["TSLA", "AMD"]}'
                out = research_node({"prompt": "momentum on tech"})
        assert out["strategy_name"] == "momentum_tech"
        assert out["symbols"] == ["TSLA", "AMD"]
        assert out["research_note"] == "LLM-extracted"
        assert "error" not in out or out.get("error") is None

    def test_llm_json_includes_optional_strategy_params(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = (
                    '{"strategy_name": "bollinger_mr", "symbols": ["XAUUSD"], '
                    '"strategy_params": {"period": 22, "std_dev": 2.0}}'
                )
                out = research_node({"prompt": "mean reversion on gold"})
        assert out["strategy_name"] == "bollinger_mr"
        assert out["symbols"] == ["XAUUSD"]
        assert out.get("strategy_params") == {"period": 22, "std_dev": 2.0}

    def test_llm_json_with_markdown_block_stripped(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = '```json\n{"strategy_name": "mean_reversion_stat_arb", "symbols": ["AAPL"]}\n```'
                out = research_node({"prompt": "stat arb"})
        assert out["strategy_name"] == "mean_reversion_stat_arb"
        assert out["symbols"] == ["AAPL"]
        assert out["research_note"] == "LLM-extracted"

    def test_llm_empty_content_returns_error(self) -> None:
        """Empty LLM response returns error; no defaults."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = ""
                out = research_node({"prompt": "stat arb tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert out.get("strategy_name") is None

    def test_llm_invalid_json_returns_error(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = "not json at all"
                out = research_node({"prompt": "tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "invalid JSON" in out.get("error", "")


    def test_llm_raises_returns_error(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.side_effect = RuntimeError("API down")
                out = research_node({"prompt": "mean reversion on tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "API down" in out.get("error", "")

    def test_empty_prompt_returns_error(self) -> None:
        """Empty prompt returns error; no defaults."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = ""
                out = research_node({"prompt": ""})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "prompt" in out.get("error", "").lower()

    def test_missing_prompt_key_returns_error(self) -> None:
        """Missing prompt key returns error."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.chat_completion") as m:
                m.return_value = ""
                out = research_node({})
        assert out["research_note"] == "error"
        assert out.get("error")

    def test_rag_stream_callback_called_for_tool_call_and_result(self) -> None:
        """When stream_callback is in state, RAG path calls it with tool_call and tool_result."""
        calls = []

        def stream_callback(event_type: str, data: dict) -> None:
            calls.append((event_type, data))

        with patch("digigraph.graph.research._digisearch_available", return_value=True):
            with patch("digigraph.graph.research._get_research_system_prompt", return_value="You have digisearch. Use it and summarize."):
                # Patch the HTTP call inside _handle_digisearch so the handler runs normally
                with patch("digigraph.orchestration.builtin.invoke_digisearch_tool", return_value={
                    "ok": True,
                    "data": {
                        "results": [{"content": "Doc 1 content", "score": 0.9, "doc_id": "d1", "rank": 1, "metadata": {}}],
                        "total": 1,
                    },
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
        backtest_payload = {"run_id": "bt-1", "status": "ok", "symbols": ["AAPL", "MSFT"]}
        # v1 missing, /backtest/start missing → synchronous /run_backtest.
        v1_response = MagicMock()
        v1_response.status_code = 404
        start_response = MagicMock()
        start_response.status_code = 404
        sync_response = MagicMock()
        sync_response.raise_for_status = MagicMock()
        sync_response.json.return_value = backtest_payload
        mock_post = MagicMock(side_effect=[v1_response, start_response, sync_response])
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                out = backtest_node({"strategy_name": "mr", "symbols": ["AAPL", "MSFT"]})
        assert out["backtest_result"] == backtest_payload
        assert out["error"] is None
        assert mock_post.call_count == 3
        assert "/v1/jobs/backtest" in str(mock_post.call_args_list[0][0][0])
        assert "/backtest/start" in str(mock_post.call_args_list[1][0][0])
        sync_call_json = mock_post.call_args_list[2][1]["json"]
        assert sync_call_json["strategy_name"] == "mr"
        assert sync_call_json["symbols"] == ["AAPL", "MSFT"]

    def test_strategy_params_included_in_payload_when_set(self) -> None:
        backtest_payload = {"run_id": "bt-2", "status": "ok", "symbols": ["GLD"]}
        v1_response = MagicMock()
        v1_response.status_code = 404
        start_response = MagicMock()
        start_response.status_code = 404
        sync_response = MagicMock()
        sync_response.raise_for_status = MagicMock()
        sync_response.json.return_value = backtest_payload
        mock_post = MagicMock(side_effect=[v1_response, start_response, sync_response])
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                backtest_node({
                    "strategy_name": "ema_cross",
                    "symbols": ["GLD"],
                    "strategy_params": {"fast_ema_period": 8, "slow_ema_period": 21},
                })
        sync_call_json = mock_post.call_args_list[2][1]["json"]
        assert sync_call_json["strategy_params"] == {"fast_ema_period": 8, "slow_ema_period": 21}

    def test_x_request_id_passed_to_digiquant_posts(self) -> None:
        """Outbound DigiQuant calls include X-Request-ID when state has request_id."""
        backtest_payload = {"run_id": "bt-1", "status": "ok", "symbols": ["AAPL"]}
        v1_response = MagicMock()
        v1_response.status_code = 404
        start_response = MagicMock()
        start_response.status_code = 404
        sync_response = MagicMock()
        sync_response.raise_for_status = MagicMock()
        sync_response.json.return_value = backtest_payload
        mock_post = MagicMock(side_effect=[v1_response, start_response, sync_response])
        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.httpx.Client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                backtest_node({
                    "strategy_name": "mr",
                    "symbols": ["AAPL"],
                    "request_id": "trace-xyz",
                })
        expected_hdrs = {"X-Request-ID": "trace-xyz"}
        for i in range(3):
            assert mock_post.call_args_list[i][1]["headers"] == expected_hdrs

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
