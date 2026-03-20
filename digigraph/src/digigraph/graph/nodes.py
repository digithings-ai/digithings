"""Graph nodes: research (LLM), backtest (DigiQuant). Phase 1."""

from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar

import httpx

# Stream callback for streaming runs. Set by workflow before invoke so the node can use it
# when LangGraph does not pass config to the node (or strips configurable).
_stream_callback_ctx: ContextVar[object | None] = ContextVar("stream_callback", default=None)

from digigraph.graph.state import WorkflowState
from digigraph.llm import chat_completion, chat_completion_with_tools, get_model_for_mode
from digigraph.tools.digisearch import digisearch

DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")


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


def _user_facing_llm_error(exc: Exception) -> str:
    """Turn LLM/provider errors into short, actionable messages for the chat."""
    msg = str(exc).lower()
    if "context window exceeds limit" in msg or "context_length_exceeded" in msg:
        return (
            "The conversation or context is too long for this model. "
            "Try: start a new chat, use a model with a larger context (e.g. set DIGI_LLM_MODE=medium), or shorten your question."
        )
    if "rate limit" in msg or "rate_limit" in msg:
        return "Rate limit reached. Please wait a moment and try again."
    if "invalid api key" in msg or "authentication" in msg or "401" in msg:
        return "API authentication failed. Check your model provider settings (e.g. OLLAMA_API_KEY, OPENAI_API_KEY)."
    return f"RAG workflow failed: {exc!s}"


def _plan_result_preview(result: str | dict) -> str:
    """Short preview of an executor step result for synthesis prompt."""
    if isinstance(result, dict):
        content = result.get("content", "")
        if isinstance(content, str) and len(content) > 400:
            content = content[:400] + "..."
        return content or json.dumps(result)[:400]
    s = str(result)
    return s[:400] + "..." if len(s) > 400 else s


def research_node(state: WorkflowState, config: dict | None = None) -> dict:
    """Data Science Family (Phase 1): use LLM to infer strategy and symbols from prompt. No fallbacks.
    LangGraph may pass config as second arg; stream_callback is read from config to avoid checkpoint serialization.
    """
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

    # RAG mode: document mode + DigiSearch → LLM calls tools via orchestration registry
    if is_document_mode and _digisearch_available():
        try:
            run_data_dir = None
            try:
                from digigraph.run_storage import get_run_data_dir
                run_data_dir = get_run_data_dir()
            except Exception:
                pass
            try:
                from digigraph.project_config import DigiProjectConfig
                index_config = DigiProjectConfig.load().get_search_index_config()
            except Exception:
                index_config = {}
            from digigraph.orchestration import ToolContext, execute
            from digigraph.skills import get_tools_for_skills

            skill_ids = ["search", "sitaas_rag"]
            try:
                from digigraph.project_config import DigiProjectConfig
                skill_ids = DigiProjectConfig.load().get_enabled_skills()
            except Exception:
                pass
            # Pass state so create_plan can store plan for executor when planning_mode is on
            context = ToolContext(
                session_id=state.get("session_id"),
                run_data_dir=run_data_dir,
                index_name=index_name,
                index_config=index_config,
                state=state,
            )
            tools_for_llm = get_tools_for_skills(skill_ids, context)
            collected_stored: dict[str, dict] = {}

            def execute_search(name: str, args: dict) -> str | dict:
                result = execute(name, args, context)
                if isinstance(result, dict) and result.get("stored_dataset_profile"):
                    p = result["stored_dataset_profile"]
                    if isinstance(p, dict) and p.get("ref"):
                        collected_stored[p["ref"]] = p
                return result

            # Prefer config so stream_callback is not in state (state gets checkpointed; msgpack cannot serialize functions).
            # Fall back to context var (set by workflow before invoke) when LangGraph does not pass config to the node.
            raw_callback = None
            if config and isinstance(config.get("configurable"), dict):
                raw_callback = config["configurable"].get("stream_callback")
            if raw_callback is None:
                raw_callback = state.get("stream_callback")
            if raw_callback is None:
                raw_callback = _stream_callback_ctx.get()

            def stream_callback(event_type: str, data: dict) -> None:
                if raw_callback is None:
                    return
                if event_type == "tool_call" and data and data.get("name") in ("digisearch", "digisearch_fetch_all"):
                    data = {**data, "index_name": index_display_name}
                raw_callback(event_type, data)

            user_content = str(prompt)
            stored = state.get("stored_datasets") or {}
            if stored and isinstance(stored, dict):
                parts = []
                max_entries = 20
                char_limit = 1200
                for ref, profile in list(stored.items())[-max_entries:]:
                    if not isinstance(profile, dict):
                        continue
                    pro = profile.get("profile") or {}
                    n = pro.get("row_count")
                    cols = pro.get("columns")
                    if isinstance(cols, list) and len(cols) > 8:
                        cols = cols[:8] + ["..."]
                    col_str = ", ".join(str(c) for c in cols[:12]) if cols else "?"
                    part = f"{ref} ({n} rows, columns: {col_str})"
                    parts.append(part)
                    if sum(len(p) for p in parts) > char_limit:
                        parts = parts[:-1]
                        parts.append("...")
                        break
                if parts:
                    user_content = (
                        "[Current session datasets: "
                        + "; ".join(parts)
                        + ". Use these dataset_refs when calling visualization_agent, analysis_agent, "
                        "data_prep_agent, data_manipulation_agent, or data_engineer_agent.]\n\n"
                        + user_content
                    )

            content = chat_completion_with_tools(
                model=get_model_for_mode(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                tools=tools_for_llm,
                execute_tool=execute_search,
                on_tool_step=stream_callback,
            )
            # Plan-and-execute: if planning_mode and create_plan stored a plan, run executor then synthesis
            planning_mode = False
            try:
                from digigraph.project_config import DigiProjectConfig
                planning_mode = DigiProjectConfig.load().get_planning_mode()
            except Exception:
                pass
            plan = state.get("plan") if isinstance(state.get("plan"), list) else None
            if planning_mode and plan:
                from digigraph.planning.executor import run_plan
                plan_results = run_plan(plan, execute_search)
                synthesis_parts = [f"Step {sid}: {_plan_result_preview(r)}" for sid, r in plan_results.items()]
                synthesis_user = (
                    "The following plan was executed. Summarize the results for the user.\n\n"
                    "Plan results:\n" + "\n".join(synthesis_parts) + "\n\nOriginal request: " + user_content
                )
                content = chat_completion(
                    get_model_for_mode(),
                    [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": synthesis_user},
                    ],
                    temperature=0.2,
                )
                content = (content or "").strip()
                state["plan"] = None
            if not content or not str(content).strip():
                return {
                    "strategy_name": None,
                    "symbols": None,
                    "research_note": "error",
                    "research_response": None,
                    "error": "LLM returned empty response. The search may have run; try rephrasing your question.",
                }
            out_state = {
                "strategy_name": None,
                "symbols": None,
                "research_note": "document-mode",
                "research_response": content.strip(),
            }
            if collected_stored:
                stored = dict(state.get("stored_datasets") or {})
                for ref, profile in collected_stored.items():
                    stored[ref] = profile
                out_state["stored_datasets"] = stored
            return out_state
        except Exception as e:
            err_msg = _user_facing_llm_error(e)
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": err_msg,
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
        err_msg = _user_facing_llm_error(e)
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "research_response": None,
            "error": err_msg,
        }


def backtest_node(state: WorkflowState) -> dict:
    """Call DigiQuant backtest; write result or error into state. Requires strategy_name and symbols.

    Uses the async /backtest/start + /backtest/{job_id}/progress SSE endpoint when available,
    falling back to the synchronous /run_backtest endpoint for older DigiQuant deployments.
    Progress events are logged at DEBUG level.
    """
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
    base_url = DIGIQUANT_URL.rstrip("/")

    try:
        with httpx.Client(timeout=60.0) as client:
            # Try async streaming path first
            start_r = client.post(f"{base_url}/backtest/start", json=payload)
            if start_r.status_code == 200:
                job_id = start_r.json().get("job_id")
                if job_id:
                    # Consume SSE progress stream (blocks until done)
                    with client.stream("GET", f"{base_url}/backtest/{job_id}/progress",
                                       timeout=90.0) as stream:
                        for line in stream.iter_lines():
                            if line.startswith("data: "):
                                try:
                                    import json as _json
                                    event = _json.loads(line[6:])
                                    logger.debug("Backtest progress [%s]: %s", job_id, event)
                                    if event.get("event") == "done":
                                        break
                                    if event.get("event") == "error":
                                        return {"backtest_result": None,
                                                "error": event.get("detail", "Backtest failed")}
                                except Exception:
                                    pass
                    # Fetch final result
                    result_r = client.get(f"{base_url}/backtest/{job_id}/result", timeout=10.0)
                    result_r.raise_for_status()
                    return {"backtest_result": result_r.json(), "error": None}

            # Fallback: synchronous endpoint (older DigiQuant or /backtest/start not available)
            r = client.post(f"{base_url}/run_backtest", json=payload, timeout=60.0)
            r.raise_for_status()
            return {"backtest_result": r.json(), "error": None}
    except Exception as e:
        return {"backtest_result": None, "error": str(e)}
