"""Phase 1: Unit tests for graph nodes (research_node, backtest_node)."""

from __future__ import annotations

from typing import Any  # score:allow
from unittest.mock import MagicMock, patch

import httpx
import pytest
from digigraph.graph.nodes import backtest_node, research_node


@pytest.mark.unit
class TestResearchNode:
    """research_node: LLM success path and error handling."""

    def test_llm_valid_json_sets_strategy_and_symbols(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = '{"strategy_name": "momentum_tech", "symbols": ["TSLA", "AMD"]}'
                out = research_node({"prompt": "momentum on tech"})
        assert out["strategy_name"] == "momentum_tech"
        assert out["symbols"] == ["TSLA", "AMD"]
        assert out["research_note"] == "LLM-extracted"
        assert "error" not in out or out.get("error") is None

    def test_llm_json_includes_optional_strategy_params(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
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
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = '```json\n{"strategy_name": "mean_reversion_stat_arb", "symbols": ["AAPL"]}\n```'
                out = research_node({"prompt": "stat arb"})
        assert out["strategy_name"] == "mean_reversion_stat_arb"
        assert out["symbols"] == ["AAPL"]
        assert out["research_note"] == "LLM-extracted"

    def test_llm_empty_content_returns_error(self) -> None:
        """Empty LLM response returns error; no defaults."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = ""
                out = research_node({"prompt": "stat arb tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert out.get("strategy_name") is None

    def test_llm_invalid_json_returns_error(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = "not json at all"
                out = research_node({"prompt": "tech"})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "invalid JSON" in out.get("error", "")


    def test_llm_raises_returns_error(self) -> None:
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.side_effect = RuntimeError("API down")
                out = research_node({"prompt": "mean reversion on tech"})
        assert out["research_note"] == "error"
        assert out.get("error") == "Research failed. Please try again shortly."
        assert "API down" not in out.get("error", "")

    def test_empty_prompt_returns_error(self) -> None:
        """Empty prompt returns error; no defaults."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = ""
                out = research_node({"prompt": ""})
        assert out["research_note"] == "error"
        assert out.get("error")
        assert "prompt" in out.get("error", "").lower()

    def test_missing_prompt_key_returns_error(self) -> None:
        """Missing prompt key returns error."""
        with patch("digigraph.graph.research.digisearch", return_value=None):
            with patch("digigraph.graph.research.completion_text") as m:
                m.return_value = ""
                out = research_node({})
        assert out["research_note"] == "error"
        assert out.get("error")

    def test_stored_datasets_prepended_to_user_content(self) -> None:
        """stored_datasets in state → LLM user message includes dataset listing."""
        stored = {
            "search_1": {
                "ref": "search_1",
                "profile": {"row_count": 42, "columns": ["ticker", "date", "close"]},
            }
        }
        _custom_prompt = "You are a research assistant. Use digisearch."
        with patch("digigraph.graph.research._digisearch_available", return_value=True):
            with patch(
                "digigraph.graph.research._load_research_settings",
                return_value=(None, "default", "default", _custom_prompt),
            ):
                with patch("digigraph.graph.research.run_tools") as mock_cwt:
                    mock_cwt.return_value = "Here is a chart summary."
                    out = research_node({"prompt": "chart search_1", "stored_datasets": stored})

        assert mock_cwt.called
        messages = mock_cwt.call_args.kwargs["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "[Current session datasets:" in user_msg
        assert "search_1" in user_msg
        assert "42 rows" in user_msg
        assert "chart search_1" in user_msg
        assert out.get("research_response") == "Here is a chart summary."

    def test_stored_datasets_absent_leaves_user_content_unchanged(self) -> None:
        """Without stored_datasets in state, user_content is plain prompt."""
        _custom_prompt = "You are a research assistant. Use digisearch."
        with patch("digigraph.graph.research._digisearch_available", return_value=True):
            with patch(
                "digigraph.graph.research._load_research_settings",
                return_value=(None, "default", "default", _custom_prompt),
            ):
                with patch("digigraph.graph.research.run_tools") as mock_cwt:
                    mock_cwt.return_value = "Plain response."
                    research_node({"prompt": "analyse AAPL"})

        messages = mock_cwt.call_args.kwargs["messages"]
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "[Current session datasets:" not in user_msg
        assert user_msg == "analyse AAPL"

    def test_stream_callback_from_state_rag_path_calls_it(self) -> None:
        """RAG path emits tool_call/tool_result via get_stream_writer() now, captured
        through the graph's own stream_mode="custom" channel — not injected via state."""
        from digigraph.graph.state import WorkflowState
        from langgraph.graph import END, START, StateGraph

        with patch("digigraph.graph.research._digisearch_available", return_value=True):
            with patch(
                "digigraph.graph.research._load_research_settings",
                return_value=(None, "default", "default", "You have digisearch. Use it and summarize."),
            ):
                with patch(
                    "digigraph.orchestration.builtin.invoke_digisearch_tool",
                    return_value={
                        "ok": True,
                        "data": {
                            "results": [
                                {
                                    "content": "Doc 1 content",
                                    "score": 0.9,
                                    "doc_id": "d1",
                                    "rank": 1,
                                    "metadata": {},
                                }
                            ],
                            "total": 1,
                        },
                    },
                ):
                    with patch("digillm.client._stream_completion_one_turn") as m:
                        m.side_effect = [
                            (
                                "",
                                [
                                    {
                                        "id": "tc1",
                                        "function": {
                                            "name": "digisearch",
                                            "arguments": '{"query": "test query"}',
                                        },
                                    }
                                ],
                            ),
                            ("Summary of the docs.", None),
                        ]
                        g: StateGraph[WorkflowState] = StateGraph(WorkflowState)
                        g.add_node("research", research_node)
                        g.add_edge(START, "research")
                        g.add_edge("research", END)
                        compiled = g.compile()
                        calls: list[tuple[str, Any]] = []
                        final: dict[str, Any] = {}
                        for part in compiled.stream(
                            {"prompt": "find docs"}, stream_mode=["updates", "custom"], version="v2"
                        ):
                            if part["type"] == "custom":
                                calls.append(part["data"])
                            else:
                                final.update(part["data"].get("research", {}))
        assert final.get("research_response") == "Summary of the docs."
        assert len(calls) >= 2
        assert calls[0][0] == "tool_call"
        assert calls[0][1].get("name") == "digisearch"
        assert calls[0][1].get("arguments", {}).get("query") == "test query"
        assert calls[1][0] == "tool_result"
        assert "Doc 1 content" in (calls[1][1].get("content") or "")

    def test_a_zero_hit_search_still_emits_a_trace(self) -> None:
        """A search that finds nothing must be visible, not silent.

        Today only rag_sources produces a span, so 'searched and found nothing' and
        'never searched' look identical in the UI — which is exactly the confusion this
        change is meant to remove.

        Drives ``_run_document_rag_path`` directly rather than ``research_node``: the
        node wraps the whole RAG path in a broad ``except Exception``, which would
        swallow an assertion failure here and report a misleading "error" state
        instead. ``run_tools`` (digillm) is faked in-line rather than imported, so we
        control exactly when ``execute_tool``/``on_tool_step`` fire without depending
        on digillm's streaming internals.

        ``_safe_stream_writer`` (not ``get_stream_writer`` directly) is patched to
        capture events: this bare call bypasses any compiled graph, so the real
        ``get_stream_writer()`` would raise (caught and no-op'd by
        ``_safe_stream_writer`` in production) -- patching the seam lets this test
        observe what the node writes without needing a full graph invocation, matching
        the single-tuple ``writer((event_type, data))`` calling convention used
        everywhere else post-migration.
        """
        from digigraph.graph.research import _run_document_rag_path

        events: list[tuple[str, object]] = []

        def fake_writer(item: tuple[str, object]) -> None:
            events.append(item)

        def fake_run_tools(
            *,
            model: str,
            messages: list[dict],
            tools: list,
            execute_tool,
            max_tool_rounds: int,
            on_tool_step,
            tool_choice: str = "auto",
        ) -> str:
            # Simulate one digillm tool round: a digisearch call that finds nothing.
            on_tool_step("tool_call", {"name": "digisearch", "arguments": {"query": "jwt"}})
            result = execute_tool("digisearch", {"query": "jwt"})
            on_tool_step("tool_result", result)
            return "No results found for jwt."

        with patch("digigraph.graph.research._safe_stream_writer", return_value=fake_writer):
            with patch("digigraph.graph.research.run_tools", side_effect=fake_run_tools):
                with patch(
                    "digigraph.orchestration.execute",
                    return_value={"results": [], "rag_sources": []},
                ):
                    out = _run_document_rag_path(
                        state={"prompt": "jwt"},
                        cfg=None,
                        system_prompt="You have digisearch. Use it and summarize.",
                        index_name="default",
                        index_display_name="default",
                        prompt="jwt",
                    )

        assert out.get("research_response") == "No results found for jwt."
        assert (
            "tool_result",
            {"results": [], "rag_sources": [], "hit_count": 0, "query": "jwt"},
        ) in events

    def test_run_document_rag_path_normalizes_empty_index_name(self) -> None:
        """#2295 review: an empty or whitespace-only index_name (e.g. a blank
        DIGISEARCH_INDEX env var) must not reach ToolContext.index_name
        unnormalized. index_name is now written unconditionally into every
        digisearch call's args (builtin.py's _handle_digisearch #2265 fix), so
        an empty ToolContext.index_name is no longer harmlessly absent —
        digisearch's own "default" fallback never gets a chance to apply."""
        from digigraph.graph.research import _run_document_rag_path

        captured: dict[str, str] = {}

        def fake_get_tools_for_skills(skill_ids: list, context: object) -> list:
            captured["index_name"] = context.index_name
            return []

        with patch("digigraph.skills.get_tools_for_skills", side_effect=fake_get_tools_for_skills):
            with patch("digigraph.graph.research.run_tools", return_value="Summary."):
                _run_document_rag_path(
                    state={"prompt": "hi"},
                    cfg=None,
                    system_prompt="sys",
                    index_name="   ",
                    index_display_name="   ",
                    prompt="hi",
                )

        assert captured["index_name"] == "default"

    def test_run_document_rag_path_normalizes_truly_empty_index_name(self) -> None:
        """Same as above for the plain-empty-string case (not just whitespace)."""
        from digigraph.graph.research import _run_document_rag_path

        captured: dict[str, str] = {}

        def fake_get_tools_for_skills(skill_ids: list, context: object) -> list:
            captured["index_name"] = context.index_name
            return []

        with patch("digigraph.skills.get_tools_for_skills", side_effect=fake_get_tools_for_skills):
            with patch("digigraph.graph.research.run_tools", return_value="Summary."):
                _run_document_rag_path(
                    state={"prompt": "hi"},
                    cfg=None,
                    system_prompt="sys",
                    index_name="",
                    index_display_name="",
                    prompt="hi",
                )

        assert captured["index_name"] == "default"


@pytest.mark.unit
class TestSupervisorNode:
    """supervisor_node: per-subject response_language preference round-trip via Store."""

    def test_supervisor_node_persists_and_recalls_response_language_per_subject(
        self,
    ) -> None:
        """A response_language preference set on one thread must be recallable on a
        brand-new thread for the same subject -- this is exactly the gap store-based
        cross-thread memory closes: workflow.py clears response_language every turn so a
        client can override it, but there was previously no cross-thread fallback, so a new
        thread for the same authenticated subject lost the preference entirely."""
        from digigraph.graph.nodes import supervisor_node
        from digigraph.graph.state import WorkflowState
        from langgraph.graph import END, START, StateGraph
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        g: StateGraph[WorkflowState] = StateGraph(WorkflowState)
        g.add_node("supervisor", supervisor_node)
        g.add_edge(START, "supervisor")
        g.add_edge("supervisor", END)
        compiled = g.compile(store=store)

        # Turn 1, thread A: subject sets a preference explicitly.
        compiled.invoke(
            {"digi_subject": "user-42", "response_language": "de"},
            config={"configurable": {"thread_id": "thread-a"}},
        )

        # Turn 2, brand-new thread B, same subject, client omits response_language entirely
        # (e.g. a fresh chat session) -- the preference must still come back.
        out = compiled.invoke(
            {"digi_subject": "user-42"},
            config={"configurable": {"thread_id": "thread-b"}},
        )
        assert out.get("response_language") == "de"

    def test_supervisor_node_store_prefs_are_isolated_across_subjects(self) -> None:
        """Store namespace is (digi_subject, \"prefs\") — subject B must never recall or
        overwrite subject A's response_language on a shared InMemoryStore. Complements
        TestDigiSubjectTrustBoundary (auth overwrite) by pinning the Store side of the
        same IDOR surface after #2354."""
        from digigraph.graph.nodes import supervisor_node
        from digigraph.graph.state import WorkflowState
        from langgraph.graph import END, START, StateGraph
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        g: StateGraph[WorkflowState] = StateGraph(WorkflowState)
        g.add_node("supervisor", supervisor_node)
        g.add_edge(START, "supervisor")
        g.add_edge("supervisor", END)
        compiled = g.compile(store=store)

        compiled.invoke(
            {"digi_subject": "user-a", "response_language": "de"},
            config={"configurable": {"thread_id": "thread-a"}},
        )

        out_b = compiled.invoke(
            {"digi_subject": "user-b"},
            config={"configurable": {"thread_id": "thread-b"}},
        )
        assert out_b.get("response_language") != "de"

        compiled.invoke(
            {"digi_subject": "user-b", "response_language": "fr"},
            config={"configurable": {"thread_id": "thread-b2"}},
        )
        out_a = compiled.invoke(
            {"digi_subject": "user-a"},
            config={"configurable": {"thread_id": "thread-a2"}},
        )
        assert out_a.get("response_language") == "de"

    def test_supervisor_node_does_not_crash_outside_a_real_graph_invocation(self) -> None:
        """Finding 3 (IMPORTANT, final whole-branch review): supervisor_node must stay
        callable/testable in isolation the same way _safe_stream_writer() already
        guarantees for get_stream_writer(). Calling it directly (bypassing
        graph.invoke()/.stream() entirely) with a digi_subject set used to reach
        get_store() outside any runnable context, which raises RuntimeError -- and even
        inside a graph compiled WITHOUT a store, get_store() returns None, and the
        subsequent store.put()/.get() would raise AttributeError. _safe_get_store()
        closes both gaps; this pins that the bare call is now safe and simply skips the
        store-dependent logic."""
        from digigraph.graph.nodes import supervisor_node

        out = supervisor_node({"digi_subject": "user-42", "response_language": "de"})

        assert "error" not in out
        # No store available -- the response_language passed in is not echoed back as
        # a fallback (there was no prior-thread value to recall), and nothing raised.
        assert "response_language" not in out
        assert out.get("supervisor_route") == "research"


@pytest.mark.unit
class TestBacktestNode:
    """backtest_node: digiquant success, timeout, 5xx, malformed response."""

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
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
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
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                backtest_node({
                    "strategy_name": "ema_cross",
                    "symbols": ["GLD"],
                    "strategy_params": {"fast_ema_period": 8, "slow_ema_period": 21},
                })
        sync_call_json = mock_post.call_args_list[2][1]["json"]
        assert sync_call_json["strategy_params"] == {"fast_ema_period": 8, "slow_ema_period": 21}

    def test_x_request_id_passed_to_digiquant_posts(self) -> None:
        """Outbound digiquant calls include X-Request-ID when state has request_id."""
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
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
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
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
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
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None

    def test_connection_error_sets_error_in_state(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        with patch("digigraph.graph.nodes.sync_client", return_value=mock_client):
            with patch("digigraph.graph.nodes.DIGIQUANT_DATA_DIR", "/tmp/data"):
                out = backtest_node({"strategy_name": "x", "symbols": ["A"]})
        assert out["backtest_result"] is None
        assert out["error"] is not None
