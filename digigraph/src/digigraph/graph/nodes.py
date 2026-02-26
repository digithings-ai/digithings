"""Graph nodes: research (LLM), backtest (DigiQuant). Phase 1."""

from __future__ import annotations

import json
import os
import re

import httpx

from digigraph.graph.state import WorkflowState
from digigraph.llm import chat_completion, chat_completion_with_tools, get_model_for_mode
from digigraph.tools.analytics.analysis import ANALYSIS_AGENT_TOOL
from digigraph.tools.analytics.data_prep import DATA_PREP_AGENT_TOOL
from digigraph.tools.analytics.visualization import VISUALIZATION_AGENT_TOOL
from digigraph.tools.digisearch import build_search_tool, digisearch

DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")


def _get_search_tool() -> dict:
    """Search tool with description and params from project index config when available."""
    try:
        from digigraph.project_config import DigiProjectConfig
        cfg = DigiProjectConfig.load()
        index_config = cfg.get_search_index_config()
        return build_search_tool(index_config)
    except Exception:
        return build_search_tool({})


def _get_search_index() -> str:
    """Index name for DigiSearch API calls. From project config (first index entry name) or DIGISEARCH_INDEX or 'default'."""
    try:
        from digigraph.project_config import DigiProjectConfig

        return DigiProjectConfig.load().get_search_index_name()
    except Exception:
        pass
    return os.environ.get("DIGISEARCH_INDEX", "default")


def _get_search_index_display_name() -> str:
    """Index name for UI display. From index definition (config_ref) index_name when present, else same as _get_search_index()."""
    try:
        from digigraph.project_config import DigiProjectConfig

        return DigiProjectConfig.load().get_search_index_display_name()
    except Exception:
        pass
    return os.environ.get("DIGISEARCH_INDEX", "default")
DIGIQUANT_DATA_DIR = os.environ.get("DIGIQUANT_DATA_DIR")

RESEARCH_SYSTEM = """You are a quant research assistant. Given a user idea for a trading strategy, respond with exactly a JSON object (no markdown, no extra text) with two keys:
- "strategy_name": snake_case name, e.g. mean_reversion_stat_arb, ema_cross, bollinger_mr
- "symbols": list of ticker symbols, e.g. ["AAPL", "MSFT", "GOOGL"]
Use the user message to infer strategy type and universe."""


def _get_research_system_prompt() -> str:
    """System prompt for research node. Custom from project config, or default quant prompt."""
    try:
        from digigraph.project_config import DigiProjectConfig

        cfg = DigiProjectConfig.load()
        custom = cfg.get_research_system_prompt()
        if custom and str(custom).strip():
            return str(custom).strip()
    except Exception:
        pass
    return RESEARCH_SYSTEM


def _digisearch_available() -> bool:
    """True when DigiSearch URL is configured."""
    url = os.environ.get("DIGISEARCH_URL", "")
    return bool(url and url.strip())


def research_node(state: WorkflowState) -> dict:
    """Data Science Family (Phase 1): use LLM to infer strategy and symbols from prompt. No fallbacks."""
    prompt = state.get("prompt")
    if not prompt or not str(prompt).strip():
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "error": "prompt required (non-empty).",
        }

    system_prompt = _get_research_system_prompt()
    is_document_mode = system_prompt != RESEARCH_SYSTEM
    index_name = _get_search_index()
    index_display_name = _get_search_index_display_name()

    # RAG mode: document mode + DigiSearch → LLM calls search tool with its own query
    if is_document_mode and _digisearch_available():
        try:
            run_data_dir = None
            try:
                from digigraph.run_storage import get_run_data_dir
                run_data_dir = get_run_data_dir()
            except Exception:
                pass
            tools_for_llm = [_get_search_tool()]
            if run_data_dir:
                tools_for_llm = tools_for_llm + [VISUALIZATION_AGENT_TOOL, ANALYSIS_AGENT_TOOL, DATA_PREP_AGENT_TOOL]

            def execute_search(name: str, args: dict) -> str | dict:
                if name == "visualization_agent":
                    from digigraph.agents.visualization import run_visualization_agent
                    result = run_visualization_agent(
                        dataset_ref=args.get("dataset_ref", ""),
                        task=args.get("task", ""),
                        session_id=state.get("session_id"),
                        options=args.get("options"),
                    )
                    return {"content": result}
                if name == "analysis_agent":
                    from digigraph.agents.analysis import run_analysis_agent
                    result = run_analysis_agent(
                        dataset_ref=args.get("dataset_ref", ""),
                        task=args.get("task", ""),
                        session_id=state.get("session_id"),
                        options=args.get("options"),
                    )
                    return {"content": result}
                if name == "data_prep_agent":
                    from digigraph.agents.data_prep import run_data_prep_agent
                    result = run_data_prep_agent(
                        dataset_ref=args.get("dataset_ref", ""),
                        task=args.get("task", ""),
                        session_id=state.get("session_id"),
                        options=args.get("options"),
                    )
                    return {"content": result}
                if name != "digisearch":
                    return f"Unknown tool: {name}"
                q = args.get("query", "")
                if not q or not str(q).strip():
                    return "No search query provided."
                top_k = args.get("top_k")
                if top_k is not None and not isinstance(top_k, int):
                    top_k = 10
                top_k = top_k if top_k is not None else 10
                data = digisearch(
                    str(q),
                    index_name=index_name,
                    top_k=top_k,
                    filter=args.get("filter"),
                    filters=args.get("filters"),
                    columns=args.get("columns"),
                    response_mode=args.get("response_mode", "full"),
                    summarize_if_over=args.get("summarize_if_over"),
                    facets=args.get("facets"),
                    highlight_fields=args.get("highlight_fields"),
                    order_by=args.get("order_by"),
                    skip=args.get("skip", 0),
                    include_total_count=args.get("include_total_count", False),
                )
                if not data:
                    return "No results found."
                results = data.get("results", [])
                summary = data.get("summary")
                # Content for LLM: include results and optional summary (data_summary, text_summary)
                payload_for_llm = {"results": results, "total": data.get("total", len(results))}
                if summary and isinstance(summary, dict):
                    payload_for_llm["summary"] = summary
                dataset_ref: str | None = None
                try:
                    from digigraph.run_storage import get_run_data_dir, write_search_results

                    if get_run_data_dir() and results:
                        dataset_ref = write_search_results(state.get("session_id"), results)
                        payload_for_llm["dataset_ref"] = dataset_ref
                except Exception:
                    pass
                if not results and not summary:
                    return "No results found."
                out: dict = {"content": json.dumps(payload_for_llm), "results": results, "summary": summary}
                if dataset_ref:
                    out["dataset_ref"] = dataset_ref
                return out

            raw_callback = state.get("stream_callback")

            def stream_callback(event_type: str, data: dict) -> None:
                if raw_callback is None:
                    return
                if event_type == "tool_call" and data and data.get("name") == "digisearch":
                    data = {**data, "index_name": index_display_name}
                raw_callback(event_type, data)

            content = chat_completion_with_tools(
                model=get_model_for_mode(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": str(prompt)},
                ],
                tools=tools_for_llm,
                execute_tool=execute_search,
                on_tool_step=stream_callback,
            )
            if not content or not str(content).strip():
                return {
                    "strategy_name": None,
                    "symbols": None,
                    "research_note": "error",
                    "research_response": None,
                    "error": "LLM returned empty response. The search may have run; try rephrasing your question.",
                }
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "document-mode",
                "research_response": content.strip(),
            }
        except Exception as e:
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": f"RAG workflow failed: {e!s}",
            }

    # Quant mode or no DigiSearch: optional search-before-LLM augmentation
    doc_context = digisearch(str(prompt), index_name=index_name, top_k=5)
    user_content = str(prompt)
    if doc_context:
        user_content = f"[Document context from DigiSearch]\n{doc_context}\n\n[User prompt]\n{prompt}"

    try:
        content = chat_completion(
            model=get_model_for_mode(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        if not content or not str(content).strip():
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": "LLM returned empty response.",
            }

        if is_document_mode:
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "document-mode",
                "research_response": content.strip(),
            }

        raw = re.sub(r"^```(?:json)?\s*", "", content).strip()
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        strategy_name = data.get("strategy_name")
        symbols = data.get("symbols")
        if not strategy_name or not isinstance(symbols, list) or not symbols:
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": "LLM response missing strategy_name or symbols (non-empty list).",
            }
        return {
            "strategy_name": str(strategy_name),
            "symbols": [str(s) for s in symbols],
            "research_note": "LLM-extracted",
        }
    except json.JSONDecodeError as e:
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "research_response": None,
            "error": f"LLM returned invalid JSON: {e!s}",
        }
    except Exception as e:
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "research_response": None,
            "error": f"LLM failed: {e!s}",
        }


def backtest_node(state: WorkflowState) -> dict:
    """Call DigiQuant run_backtest; write result or error into state. Requires strategy_name and symbols."""
    if state.get("error"):
        return {"backtest_result": None, "error": state.get("error")}
    strategy_name = state.get("strategy_name")
    symbols = state.get("symbols")
    if not strategy_name or not symbols or not isinstance(symbols, list) or len(symbols) == 0:
        return {
            "backtest_result": None,
            "error": "strategy_name and symbols (non-empty list) required. Research node must provide them.",
        }
    if not DIGIQUANT_DATA_DIR:
        return {
            "backtest_result": None,
            "error": "DIGIQUANT_DATA_DIR env required. Set path to directory with {symbol}.csv files.",
        }
    payload: dict = {"strategy_name": strategy_name, "symbols": symbols, "data_dir": DIGIQUANT_DATA_DIR}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{DIGIQUANT_URL.rstrip('/')}/run_backtest",
                json=payload,
            )
            r.raise_for_status()
            backtest = r.json()
        return {"backtest_result": backtest, "error": None}
    except Exception as e:
        return {"backtest_result": None, "error": str(e)}
