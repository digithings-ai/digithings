"""Research node: document RAG (tool loop), quant JSON extraction, and digisearch-augmented prompts."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from langgraph.config import get_store, get_stream_writer
from langgraph.store.base import BaseStore
from langgraph.types import StreamWriter

from digigraph.boundaries import PROJECT_CONFIG_ERRORS
from digigraph.chat_prompt import last_user_turn
from digigraph.compaction import (
    compact_messages,
    compaction_config_from_env,
)
from digigraph.filter_hints import extract_filter_hints
from digigraph.graph.state import WorkflowState
from digigraph.languages import resolve_language_directive
from digigraph.llm_client import completion_text, run_tools
from digigraph.model_config import get_model_for_mode
from digigraph.project_config import DigiProjectConfig
from digigraph.retrieval import (
    auto_load_notes,
    force_tool_messages,
    query_from_tool_args,
    resolve_force_tool,
)
from digigraph.tool_policy import frozen_from_state_list
from digigraph.tools.digisearch import digisearch
from digigraph.trace_events import merge_rag_sources_accumulator

logger = logging.getLogger(__name__)


def _safe_stream_writer() -> StreamWriter:
    """get_stream_writer() raises RuntimeError when called outside a compiled graph's
    invocation (e.g. a unit test calling a node function directly, bypassing
    graph.invoke()/.stream()) -- catch that and fall back to a true no-op, so node
    logic stays testable in isolation without needing a full graph invocation."""
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _data: None


def _safe_get_store() -> BaseStore | None:
    """get_store() raises RuntimeError when called outside a compiled graph's
    invocation (e.g. a unit test calling a node function directly, or any other
    out-of-runnable-context call) -- catch that and return None, mirroring
    _safe_stream_writer()'s pattern so node logic stays testable/callable in
    isolation without needing a real graph invocation.

    Also covers the in-graph case where the compiled graph has no store attached
    at all: LangGraph's get_store() returns None then (no exception), which a bare
    ``store.put(...)``/``store.get(...)`` call would turn into an AttributeError.
    Callers must treat a None return here the same as "no store available" and
    skip the store-dependent logic, exactly as if the calling condition (e.g.
    ``if subject:``) were false.
    """
    try:
        return get_store()
    except RuntimeError:
        return None


RESEARCH_SYSTEM = """You are a quant research assistant. Given a user idea for a trading strategy, respond with exactly one JSON object (no markdown fences, no prose before or after) with keys:
- "strategy_name": snake_case name, e.g. mean_reversion_stat_arb, ema_cross, bollinger_mr
- "symbols": JSON array of uppercase ticker strings only, e.g. ["AAPL","MSFT","GOOGL"] — never a single comma-separated string
- "strategy_params": optional object mapping parameter names to numbers or strings, e.g. {"fast_ema_period": 12, "slow_ema_period": 26, "trade_size": 1000}. Omit or use {} if unsure.
If the user names tickers or a universe, every symbol must appear in "symbols". If they only describe a strategy without tickers, infer a sensible small basket (e.g. large-cap tech for a generic equity idea)."""


def _coerce_strategy_params(raw: object) -> dict[str, float | int | str] | None:
    """Normalize LLM-provided strategy_params for digiquant (flat JSON numbers/strings only)."""
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


def _user_facing_llm_error(exc: Exception) -> tuple[str, str | None]:
    """Return ``(message, error_code)`` for an LLM failure.

    ``error_code`` is a stable digichat contract value (e.g. ``free_quota_exceeded``)
    or ``None`` when the failure is unclassified.
    """
    from digigraph.llm_errors import (
        FREE_QUOTA_EXCEEDED,
        RATE_LIMIT,
        classify_llm_error,
        free_quota_message,
        rate_limit_message,
    )

    code = classify_llm_error(exc)
    if code == FREE_QUOTA_EXCEEDED:
        return free_quota_message(), FREE_QUOTA_EXCEEDED
    if code == RATE_LIMIT:
        return rate_limit_message(), RATE_LIMIT

    msg = str(exc).lower()
    if "context window exceeds limit" in msg or "context_length_exceeded" in msg:
        return (
            "The conversation or context is too long for this model. "
            "Try: start a new chat, use a model with a larger context (e.g. set DIGI_LLM_MODE=medium), or shorten your question.",
            None,
        )
    if "invalid api key" in msg or "authentication" in msg or "401" in msg:
        return (
            "API authentication failed. Check your model provider settings (e.g. OLLAMA_API_KEY, OPENAI_API_KEY).",
            None,
        )
    if _is_likely_network_failure(exc):
        base = (os.environ.get("OPENAI_API_BASE") or "").strip() or "(unset — OpenAI default URL)"
        vert = _vertical_url_host_hints()
        if vert:
            # Operator diagnostics only — never stream Docker Compose hostnames to embed clients.
            logger.warning("research network failure host hints: %s", vert)
        return (
            "A network connection failed during research (LLM and/or tools calling digisearch). "
            f"OPENAI_API_BASE is {base}. "
            "Start LiteLLM (http://127.0.0.1:4000/v1) or Ollama (http://127.0.0.1:11434/v1) and ensure digigraph can reach it. "
            "Document/RAG also needs digisearch orchestrator at DIGISEARCH_URL (host: http://127.0.0.1:8002). "
            "If you use `make stack-local`, host.docker.internal in OPENAI_API_BASE is rewritten to 127.0.0.1. "
            "See docs/LOCAL_STACK.md.",
            None,
        )
    tail = _vertical_url_host_hints()
    if tail:
        logger.warning("research failure host hints: %s", tail)
    # Never echo raw exception text (may include Compose service DNS names like digisearch:8002).
    return "Research failed. Please try again shortly.", None


def _plan_result_preview(result: str | dict) -> str:
    if isinstance(result, dict):
        content = result.get("content", "")
        if isinstance(content, str) and len(content) > 400:
            content = content[:400] + "..."
        return content or json.dumps(result)[:400]
    s = str(result)
    return s[:400] + "..." if len(s) > 400 else s


def _tool_name(tool: dict[str, Any] | str) -> str | None:
    """Extract the orchestrator tool name from an OpenAI tool dict or SUMMARY string."""
    if isinstance(tool, str):
        return tool.split(":", 1)[0].strip() or None
    if not isinstance(tool, dict):
        return None
    fn = tool.get("function")
    if isinstance(fn, dict):
        name = fn.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    name = tool.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _run_document_rag_path(
    *,
    state: WorkflowState,
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

    skill_ids = list(cfg.get_enabled_skills() if cfg else ["search", "project_rag"])
    # Opt-in web skill (#3420) — not in digiproject.yaml by default; appended only
    # when this request enabled web search so corpus-only deploys stay corpus-only.
    if state.get("enable_web_search") and "web" not in skill_ids:
        skill_ids.append("web")

    # Distinguish None (unrestricted) from [] (deny-all). A falsy check coerces
    # empty allowlist → None and silently opens every tool — the documented
    # contract is the opposite (ARCHITECTURE § tool allowlist; tool_policy).
    _allowed_names = frozen_from_state_list(state.get("allowed_tool_names"))
    _ctx_rid = state.get("request_id")
    _ctx_wid = state.get("workflow_id")
    # Normalize before constructing ToolContext (#2295 review): an empty or
    # whitespace-only DIGISEARCH_INDEX (e.g. `DIGISEARCH_INDEX=""` in the
    # environment) flows straight through `_load_research_settings()` into
    # `index_name` here unstripped. digisearch happens to fall back to "default"
    # server-side, but `ToolContext.index_name` should never carry an empty
    # value — it is now written unconditionally into every digisearch call's
    # args (`_handle_digisearch`'s #2265 fix), so an empty value here is no
    # longer harmlessly absent.
    _resolved_index_name = str(index_name).strip() or "default"
    context = ToolContext(
        session_id=state.get("session_id"),
        run_data_dir=run_data_dir,
        index_name=_resolved_index_name,
        index_config=index_config,
        state=state,
        allowed_tool_names=_allowed_names,
        request_id=None if _ctx_rid is None else (str(_ctx_rid).strip() or None),
        workflow_id=None if _ctx_wid is None else (str(_ctx_wid).strip() or None),
        vault_path_prefix=(
            str(state["vault_path_prefix"]).strip() if state.get("vault_path_prefix") else None
        )
        or None,
    )
    tools_for_llm = get_tools_for_skills(skill_ids, context)
    collected_stored: dict[str, dict] = {}
    collected_rag: list[dict] = []

    writer = _safe_stream_writer()

    def stream_callback(event_type: str, data: Any) -> None:
        if (
            event_type == "tool_call"
            and data
            and data.get("name") in ("digisearch", "digisearch_fetch_all")
        ):
            data = {**data, "index_name": index_display_name}
        writer((event_type, data))

    def execute_one(name: str, args: dict) -> str | dict:
        result = execute(name, args, context)
        if isinstance(result, dict) and result.get("stored_dataset_profile"):
            p = result["stored_dataset_profile"]
            if isinstance(p, dict) and p.get("ref"):
                collected_stored[p["ref"]] = p
        if isinstance(result, dict) and result.get("rag_sources"):
            # WorkflowState stays lean — full get_note bodies stream on the
            # rag_sources trace for digichat DocumentPane (#3419) but must not
            # enter LangGraph checkpoints.
            lean_sources = [
                {k: v for k, v in item.items() if k != "body"} if isinstance(item, dict) else item
                for item in result["rag_sources"]
            ]
            merge_rag_sources_accumulator(collected_rag, lean_sources)
        # Make every tool call visible in the activity UI, including zero-hit
        # searches: without hit_count, "searched and found nothing" and "never
        # searched" look identical downstream. setdefault so a tool that already
        # sets these (e.g. a future handler) is not clobbered.
        if isinstance(result, dict):
            result.setdefault("hit_count", len(result.get("rag_sources") or []))
            query_arg = query_from_tool_args(args)
            if query_arg:
                result.setdefault("query", query_arg)
        return result

    def execute_search(name: str, args: dict) -> str | dict:
        result = execute_one(name, args)
        if isinstance(result, dict):
            # #3417: load full notes after a locate so the model synthesizes
            # instead of asking permission to read what it already found.
            result = auto_load_notes(
                locate_tool=name,
                locate_result=result,
                execute_fn=execute_one,
                emit=stream_callback,
                allowed_names=_allowed_names,
            )
        return result

    user_content = str(prompt)

    # Project mode only: prepend NL filter hints so the LLM folds them into
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

    # The model drives retrieval: it chooses whether to search, writes its own query,
    # and may follow a digisearch hit with digivault_get_note to read the whole note.
    # 4 rounds is enough for locate -> load -> answer with one retry. This bounds
    # tool-calling rounds, not the completion count outright: run_tools unconditionally
    # fires one extra tool-free completion to synthesize a final answer once the round
    # budget is exhausted (digillm/src/digillm/client.py, run_tools' post-loop handling),
    # so a fully-exhausted budget costs exactly 5 completions per turn (this used to be
    # exactly 1).
    #
    # Two-tier compaction (#399): prior-turn ``llm_messages`` (when present) plus the
    # current system/user pair are compacted *before* digillm sees them.
    # Do **not** wrap ``execute_search`` with ``wrap_execute_tool_for_tier1``: that
    # replaced same-turn digisearch payloads (>2 KB) with workspace stubs the model
    # cannot read, so project-mode RAG answers were synthesized from stubs alone.
    # digillm already caps injected tool text via ``DIGI_TOOL_MESSAGE_MAX_CHARS``.
    # The checkpoint keeps ``_compaction_event`` (refs only); originals live under
    # the session workspace when tier-1/2 run on the pre-LLM message list.
    compaction_cfg = compaction_config_from_env()
    prior = state.get("llm_messages")
    base_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    if isinstance(prior, list) and prior:
        # Drop a trailing system duplicate if the prior turn already carried one.
        base_messages = [m for m in prior if isinstance(m, dict)] + [
            {"role": "user", "content": user_content},
        ]
    compaction = compact_messages(
        base_messages,
        compaction_cfg,
        session_id=state.get("session_id"),
    )
    llm_messages = list(compaction.llm_messages)
    forced = resolve_force_tool(state.get("force_tool"))
    force_query = last_user_turn(str(prompt))
    # Skip inject when the tenant allowlist excludes the tool. execute() would
    # deny it anyway, but we must not emit a started tool_call / Searching…
    # row or feed the deny blob into force_tool_messages. None = unrestricted
    # (public embed); a set must contain the forced tool.
    if forced and force_query and (_allowed_names is None or forced in _allowed_names):
        # #3418: inject the locate call with the user string as the argument.
        # Do not hint the model — it only synthesizes after the result lands.
        hop_args = {"query": force_query}
        stream_callback("tool_call", {"name": forced, "arguments": hop_args})
        forced_result = execute_search(forced, hop_args)
        if isinstance(forced_result, dict):
            stream_callback("tool_result", {**forced_result, "name": forced})
            llm_messages.extend(force_tool_messages(forced, force_query, forced_result))
        else:
            stream_callback("tool_result", {"name": forced, "content": str(forced_result)})
            llm_messages.extend(
                force_tool_messages(forced, force_query, {"content": str(forced_result)})
            )
    content = run_tools(
        model=get_model_for_mode(),
        messages=llm_messages,
        tools=tools_for_llm,
        execute_tool=execute_search,
        max_tool_rounds=4,
        on_tool_step=stream_callback,
        tool_choice="auto"
        if forced
        else ("required" if state.get("require_tool_calls") else "auto"),
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
        content = completion_text(
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
        # Persist the compacted LLM view for the next turn (non-destructive: originals
        # are in the workspace via `_compaction_event` refs when compaction ran).
        "llm_messages": compaction.llm_messages,
    }
    if compaction.event is not None:
        out_state["_compaction_event"] = compaction.event.model_dump()
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
            f"[Document context from digisearch]\n{doc_context}\n\n[User prompt]\n{prompt}"
        )

    try:
        content = completion_text(
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
        err_msg, err_code = _user_facing_llm_error(e)
        out: dict = {
            "strategy_name": None,
            "symbols": None,
            "research_note": "error",
            "research_response": None,
            "error": err_msg,
        }
        if err_code:
            out["error_code"] = err_code
        return out


def research_node(state: WorkflowState) -> dict:
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
    override_index = state.get("digisearch_index")
    if override_index and str(override_index).strip():
        index_name = str(override_index).strip()
        index_display_name = index_name
    override_prompt = state.get("research_system_prompt_override")
    if override_prompt and str(override_prompt).strip():
        system_prompt = str(override_prompt).strip()
    is_document_mode = system_prompt != RESEARCH_SYSTEM

    language_directive = resolve_language_directive(state.get("response_language"))
    if language_directive:
        system_prompt = f"{system_prompt}\n\n{language_directive}"

    if is_document_mode and _digisearch_available():
        try:
            return _run_document_rag_path(
                state=state,
                cfg=cfg,
                system_prompt=system_prompt,
                index_name=index_name,
                index_display_name=index_display_name,
                prompt=str(prompt),
            )
        except Exception as e:
            err_msg, err_code = _user_facing_llm_error(e)
            out: dict = {
                "strategy_name": None,
                "symbols": None,
                "research_note": "error",
                "research_response": None,
                "error": err_msg,
            }
            if err_code:
                out["error_code"] = err_code
            return out

    # Scope warning, not a guard. `require_tool_calls` is wired into exactly one
    # tool loop -- the document RAG path above. This path, and the sub-agent runners
    # under digigraph/agents/*, run at tool_choice="auto" regardless. An operator who
    # sets DIGI_REQUIRE_TOOL_CALLS=true as a grounding mandate would otherwise get a
    # silent no-op here (e.g. DIGISEARCH_URL unset, so _digisearch_available() is
    # False and every request falls through). Log it rather than fail the request:
    # the flag is advisory outside the RAG path today. Central enforcement is #2384.
    if state.get("require_tool_calls"):
        logger.warning(
            "require_tool_calls=true but this request took the quant/augmented path, "
            "which does not enforce tool_choice; the grounding mandate is not applied "
            "(is_document_mode=%s, digisearch_available=%s)",
            is_document_mode,
            _digisearch_available(),
        )

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
