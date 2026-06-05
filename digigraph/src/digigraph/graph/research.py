"""Research node: document RAG (tool loop), quant JSON extraction, and DigiSearch-augmented prompts."""

from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from typing import Any

from digigraph.boundaries import PROJECT_CONFIG_ERRORS
from digigraph.filter_hints import extract_filter_hints
from digigraph.graph.state import WorkflowState
from digigraph.llm import chat_completion, chat_completion_with_tools, get_model_for_mode
from digigraph.project_config import DigiProjectConfig
from digigraph.tools.digisearch import digisearch
from digigraph.trace_events import merge_rag_sources_accumulator

logger = logging.getLogger(__name__)

# Stream callback for streaming runs. Set by workflow before invoke so the node can use it
# when LangGraph does not pass config to the node (or strips configurable).
_stream_callback_ctx: ContextVar[object | None] = ContextVar("stream_callback", default=None)

RESEARCH_SYSTEM = """You are a quant research assistant. Given a user idea for a trading strategy, respond with exactly one JSON object (no markdown fences, no prose before or after) with keys:
- "strategy_name": snake_case name, e.g. mean_reversion_stat_arb, ema_cross, bollinger_mr
- "symbols": JSON array of uppercase ticker strings only, e.g. ["AAPL","MSFT","GOOGL"] — never a single comma-separated string
- "strategy_params": optional object mapping parameter names to numbers or strings, e.g. {"fast_ema_period": 12, "slow_ema_period": 26, "trade_size": 1000}. Omit or use {} if unsure.
If the user names tickers or a universe, every symbol must appear in "symbols". If they only describe a strategy without tickers, infer a sensible small basket (e.g. large-cap tech for a generic equity idea)."""


def _coerce_strategy_params(raw: object) -> dict[str, float | int | str] | None:
    """Normalize LLM-provided strategy_params for DigiQuant (flat JSON numbers/strings only)."""
    if raw is None:
        return None
    if isinstance(raw, dict) and len(raw) == 0:
        return None
    if not isinstance(raw, dict):
        return None
    out: dict[str, float | int | str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if isinstance(v, bool):
            out[k] = int(v)
        elif isinstance(v, int):
            out[k] = v
        elif isinstance(v, float):
            out[k] = v
        elif isinstance(v, str):
            out[k] = v
    return out or None


def _strip_json_fence_llm(raw: str) -> str:
    s = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip()).strip()
    return re.sub(r"\s*```$", "", s).strip()


def _parse_llm_json_object(content: str) -> dict[str, Any]:
    """Parse one JSON object from model output; allow fences, preamble, or trailing text."""
    s = _strip_json_fence_llm(content)
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found in model response", s, 0)
    obj, _ = decoder.raw_decode(s, start)
    if isinstance(obj, dict):
        return obj
    raise json.JSONDecodeError("Top-level JSON is not an object", s, start)


def _unwrap_quant_payload(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("result", "output", "data", "strategy", "extract"):
        inner = data.get(key)
        if isinstance(inner, dict) and any(
            k in inner for k in ("strategy_name", "strategy", "symbols", "tickers", "universe")
        ):
            return inner
    return data


def _pick_strategy_name(data: dict[str, Any]) -> str | None:
    for key in ("strategy_name", "strategy", "catalog_strategy", "name"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _coerce_symbols_from_llm(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip().upper() for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str):
        parts = re.split(r"[,;]+|\s+", raw.strip())
        return [p.strip().upper() for p in parts if p.strip()]
    return []


def _load_research_settings() -> tuple[DigiProjectConfig | None, str, str, str]:
    """Load project config once; return (cfg, index_name, index_display_name, system_prompt)."""
    default_index = os.environ.get("DIGISEARCH_INDEX", "default")
    try:
        cfg = DigiProjectConfig.load()
    except PROJECT_CONFIG_ERRORS as exc:
        logger.debug("DigiProjectConfig.load failed: %s", exc)
        return None, default_index, default_index, RESEARCH_SYSTEM
    index_name = cfg.get_search_index_name()
    index_display = cfg.get_search_index_display_name()
    system_prompt = RESEARCH_SYSTEM
    custom = cfg.get_research_system_prompt()
    if custom and str(custom).strip():
        system_prompt = str(custom).strip()
    return cfg, index_name, index_display, system_prompt


def _digisearch_available() -> bool:
    url = os.environ.get("DIGISEARCH_URL", "")
    return bool(url and url.strip())


def _vertical_url_host_hints() -> str:
    """Warn when Compose-style hostnames are set but the stack runs on the host."""
    parts: list[str] = []
    ds = (os.environ.get("DIGISEARCH_URL") or "").strip().lower()
    dq = (os.environ.get("DIGIQUANT_URL") or "").strip().lower()
    if (
        "://digisearch" in ds
        or ds.startswith("http://digisearch")
        or ds.startswith("https://digisearch")
    ):
        parts.append(
            "DIGISEARCH_URL uses the Docker hostname `digisearch`, which does not resolve on the host. "
            "For `make stack-local` set DIGISEARCH_URL=http://127.0.0.1:8002 in repo-root `.env` (run_stack_local.sh exports this for its children; IDE/manual uvicorn may still load the Docker value)."
        )
    if "://digiquant" in dq or dq.startswith("http://digiquant"):
        parts.append(
            "DIGIQUANT_URL uses `digiquant`; on the host use http://127.0.0.1:8001 unless you have that name in /etc/hosts."
        )
    return " ".join(parts)


def _is_likely_network_failure(exc: Exception) -> bool:
    """Detect LLM client / httpx connection failures (including wrappers with empty str)."""
    chunks: list[str] = [str(exc)]
    c = exc.__cause__
    depth = 0
    while c is not None and depth < 4:
        chunks.append(str(c))
        c = getattr(c, "__cause__", None)
        depth += 1
    msg = " ".join(chunks).lower()
    needles = (
        "connection error",
        "connection refused",
        "failed to connect",
        "errno 61",
        "errno 111",
        "name or service not known",
        "nodename nor servname",
        "temporary failure in name resolution",
        "getaddrinfo failed",
        "network is unreachable",
        "read timed out",
        "connect timeout",
        "timed out",
    )
    if any(n in msg for n in needles):
        return True
    try:
        from openai import APIConnectionError as _OpenAIAPIConnectionError

        if isinstance(exc, _OpenAIAPIConnectionError):
            return True
    except ImportError:
        pass
    try:
        import httpx

        if isinstance(
            exc,
            (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException),
        ):
            return True
    except ImportError:
        pass
    return False


def _user_facing_llm_error(exc: Exception) -> str:
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
    if _is_likely_network_failure(exc):
        base = (os.environ.get("OPENAI_API_BASE") or "").strip() or "(unset — OpenAI default URL)"
        vert = _vertical_url_host_hints()
        return (
            "A network connection failed during research (LLM and/or tools calling DigiSearch). "
            f"OPENAI_API_BASE is {base}. "
            "Start LiteLLM (http://127.0.0.1:4000/v1) or Ollama (http://127.0.0.1:11434/v1) and ensure DigiGraph can reach it. "
            "Document/RAG also needs DigiSearch orchestrator at DIGISEARCH_URL (host: http://127.0.0.1:8002). "
            + (vert + " " if vert else "")
            + "If you use `make stack-local`, host.docker.internal in OPENAI_API_BASE is rewritten to 127.0.0.1. "
            "See docs/LOCAL_STACK.md."
        )
    tail = _vertical_url_host_hints()
    if tail:
        return f"RAG workflow failed: {exc!s} {tail}"
    return f"RAG workflow failed: {exc!s}"


def _plan_result_preview(result: str | dict) -> str:
    if isinstance(result, dict):
        content = result.get("content", "")
        if isinstance(content, str) and len(content) > 400:
            content = content[:400] + "..."
        return content or json.dumps(result)[:400]
    s = str(result)
    return s[:400] + "..." if len(s) > 400 else s


def _run_document_rag_path(
    *,
    state: WorkflowState,
    config: dict | None,
    cfg: DigiProjectConfig | None,
    system_prompt: str,
    index_name: str,
    index_display_name: str,
    prompt: str,
) -> dict:
    run_data_dir = None
    try:
        from digigraph.run_storage import get_run_data_dir

        run_data_dir = get_run_data_dir()
    except Exception as exc:
        logger.debug("get_run_data_dir: %s", exc)

    index_config: dict = {}
    if cfg:
        try:
            index_config = cfg.get_search_index_config()
        except Exception as exc:
            logger.debug("get_search_index_config: %s", exc)

    from digigraph.orchestration import ToolContext, execute
    from digigraph.skills import get_tools_for_skills

    skill_ids = cfg.get_enabled_skills() if cfg else ["search", "sitaas_rag"]

    _raw_allowed = state.get("allowed_tool_names")
    _allowed_names = frozenset(_raw_allowed) if _raw_allowed else None
    _ctx_rid = state.get("request_id")
    _ctx_wid = state.get("workflow_id")
    context = ToolContext(
        session_id=state.get("session_id"),
        run_data_dir=run_data_dir,
        index_name=index_name,
        index_config=index_config,
        state=state,
        allowed_tool_names=_allowed_names,
        request_id=None if _ctx_rid is None else (str(_ctx_rid).strip() or None),
        workflow_id=None if _ctx_wid is None else (str(_ctx_wid).strip() or None),
    )
    tools_for_llm = get_tools_for_skills(skill_ids, context)
    collected_stored: dict[str, dict] = {}
    collected_rag: list[dict] = []

    def execute_search(name: str, args: dict) -> str | dict:
        result = execute(name, args, context)
        if isinstance(result, dict) and result.get("stored_dataset_profile"):
            p = result["stored_dataset_profile"]
            if isinstance(p, dict) and p.get("ref"):
                collected_stored[p["ref"]] = p
        if isinstance(result, dict) and result.get("rag_sources"):
            merge_rag_sources_accumulator(collected_rag, result["rag_sources"])
        return result

    raw_callback = None
    if config and isinstance(config.get("configurable"), dict):
        raw_callback = config["configurable"].get("stream_callback")
    if raw_callback is None:
        raw_callback = state.get("stream_callback")
    if raw_callback is None:
        raw_callback = _stream_callback_ctx.get()

    def stream_callback(event_type: str, data: Any) -> None:
        if raw_callback is None:
            return
        if (
            event_type == "tool_call"
            and data
            and data.get("name") in ("digisearch", "digisearch_fetch_all")
        ):
            data = {**data, "index_name": index_display_name}
        raw_callback(event_type, data)

    user_content = str(prompt)

    # SITAAS-only (project mode): prepend NL filter hints so the LLM folds them into
    # digisearch tool args. Opt out via DIGI_FILTER_HINTS=0. extract_filter_hints is fail-open.
    if run_data_dir:
        hint_block = extract_filter_hints(user_content).as_context_block()
        if hint_block:
            user_content = hint_block + "\n\n" + user_content

    stored = state.get("stored_datasets") or {}
    if stored and isinstance(stored, dict):
        parts: list[str] = []
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

    planning_mode = bool(cfg.get_planning_mode()) if cfg else False
    plan = state.get("plan") if isinstance(state.get("plan"), list) else None
    if planning_mode and plan:
        from digigraph.planning.executor import run_plan

        plan_results = run_plan(plan, execute_search)
        synthesis_parts = [
            f"Step {sid}: {_plan_result_preview(r)}" for sid, r in plan_results.items()
        ]
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
    out_state: dict = {
        "strategy_name": None,
        "symbols": None,
        "research_note": "document-mode",
        "research_response": content.strip(),
    }
    if collected_stored:
        merged = dict(state.get("stored_datasets") or {})
        for ref, profile in collected_stored.items():
            merged[ref] = profile
        out_state["stored_datasets"] = merged
    if collected_rag:
        out_state["rag_sources"] = collected_rag

    return out_state


def _run_quant_or_augmented_path(
    *,
    system_prompt: str,
    index_name: str,
    prompt: str,
    is_document_mode: bool,
    request_id: str | None = None,
    authorization_bearer: str | None = None,
) -> dict:
    doc_context = digisearch(
        str(prompt),
        index_name=index_name,
        top_k=5,
        request_id=request_id,
        authorization_bearer=authorization_bearer,
    )
    user_content = str(prompt)
    if doc_context:
        user_content = (
            f"[Document context from DigiSearch]\n{doc_context}\n\n[User prompt]\n{prompt}"
        )

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

        try:
            data = _parse_llm_json_object(content)
        except json.JSONDecodeError as parse_err:
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": (content or "").strip()[:12000],
                "error": f"LLM returned invalid JSON: {parse_err!s}",
            }

        data = _unwrap_quant_payload(data)
        strategy_name = _pick_strategy_name(data)
        symbols: list[str] = []
        for sk in ("symbols", "tickers", "universe", "instrument_ids"):
            symbols = _coerce_symbols_from_llm(data.get(sk))
            if symbols:
                break
        if not strategy_name or not symbols:
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": (content or "").strip()[:12000],
                "error": (
                    "LLM response missing strategy_name or symbols (non-empty list). "
                    "Name at least one ticker (e.g. AAPL) and a strategy style, or switch workflow to "
                    "research_rag / document mode if you only want Q&A without backtest."
                ),
            }
        out: dict = {
            "strategy_name": str(strategy_name),
            "symbols": symbols,
            "research_note": "LLM-extracted",
        }
        sp = _coerce_strategy_params(data.get("strategy_params"))
        if sp:
            out["strategy_params"] = sp
        return out
    except Exception as e:
        err_msg = _user_facing_llm_error(e)
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "research_response": None,
            "error": err_msg,
        }


def research_node(state: WorkflowState, config: dict | None = None) -> dict:
    """Data Science Family (Phase 1): LLM infers strategy/symbols or document-mode RAG with tools."""
    prompt = state.get("prompt")
    if not prompt or not str(prompt).strip():
        return {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "error": "prompt required (non-empty).",
        }

    cfg, index_name, index_display_name, system_prompt = _load_research_settings()
    is_document_mode = system_prompt != RESEARCH_SYSTEM

    if is_document_mode and _digisearch_available():
        try:
            return _run_document_rag_path(
                state=state,
                config=config,
                cfg=cfg,
                system_prompt=system_prompt,
                index_name=index_name,
                index_display_name=index_display_name,
                prompt=str(prompt),
            )
        except Exception as e:
            err_msg = _user_facing_llm_error(e)
            return {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": err_msg,
            }

    _req_rid = state.get("request_id")
    _norm_rid = None if _req_rid is None else (str(_req_rid).strip() or None)
    return _run_quant_or_augmented_path(
        system_prompt=system_prompt,
        index_name=index_name,
        prompt=str(prompt),
        is_document_mode=is_document_mode,
        request_id=_norm_rid,
        authorization_bearer=state.get("digi_bearer"),
    )
