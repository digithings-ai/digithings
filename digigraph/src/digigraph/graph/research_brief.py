"""Build ResearchBrief from RAG synthesis + source list; optional quant field extraction."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from digigraph.graph.research import (
    RESEARCH_SYSTEM,
    _coerce_strategy_params,
    _coerce_symbols_from_llm,
    _parse_llm_json_object,
    _pick_strategy_name,
    _unwrap_quant_payload,
)
from digigraph.graph.state import WorkflowState
from digigraph.llm import chat_completion, get_model_for_mode
from digigraph.research_brief_models import (
    BRIEF_SYSTEM,
    ResearchBrief,
    parse_brief_from_llm,
    research_brief_graph_patch,
)
from digigraph.trace_events import TraceEventV1
from digigraph.trading_profile import profiling_questions_for_workflow

logger = logging.getLogger(__name__)


def _extract_enabled() -> bool:
    return os.environ.get("DIGI_EXTRACT_STRATEGY_AFTER_DOCUMENT_RAG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _resolve_stream_callback(state: WorkflowState, config: dict | None) -> Any:
    cb = None
    if config and isinstance(config.get("configurable"), dict):
        cb = config["configurable"].get("stream_callback")
    if cb is None:
        cb = state.get("stream_callback")
    if cb is None:
        from digigraph.graph.research import _stream_callback_ctx

        cb = _stream_callback_ctx.get()
    return cb


def _legacy_json_extract_after_brief(
    *, user_prompt: str, synthesis: str, brief: ResearchBrief
) -> dict[str, Any] | None:
    """Second LLM call: JSON strategy_name/symbols when brief did not fill them."""
    try:
        extract_prompt = (
            f"{RESEARCH_SYSTEM}\n\nUser request:\n{user_prompt}\n\n"
            f"Research brief themes (for context only; do not contradict JSON shape):\n"
            f"{brief.model_dump_json()[:6000]}\n\nAssistant synthesis:\n{synthesis[:8000]}\n\n"
            "Respond with only the JSON object."
        )
        extract_raw = chat_completion(
            get_model_for_mode(),
            [{"role": "user", "content": extract_prompt}],
            temperature=0.0,
        )
        data = _parse_llm_json_object(extract_raw or "")
        data = _unwrap_quant_payload(data)
        sname = _pick_strategy_name(data)
        syms: list[str] = []
        for sk in ("symbols", "tickers", "universe", "instrument_ids"):
            syms = _coerce_symbols_from_llm(data.get(sk))
            if syms:
                break
        if sname and syms:
            out: dict[str, Any] = {
                "strategy_name": str(sname),
                "symbols": syms,
            }
            sp = _coerce_strategy_params(data.get("strategy_params"))
            if sp:
                out["strategy_params"] = sp
            return out
    except Exception as exc:
        logger.debug("legacy JSON extract after brief failed: %s", exc)
    return None


def research_brief_builder_node(state: WorkflowState, config: dict | None = None) -> dict[str, Any]:
    """Emit ResearchBrief + merged profiling questions; optionally fill quant fields from brief or legacy extract."""
    if state.get("error"):
        return {}
    synthesis = (state.get("research_response") or "").strip()
    rag = state.get("rag_sources")
    if not synthesis and not (isinstance(rag, list) and rag):
        return {}

    allowed_ids: list[str] = []
    if isinstance(rag, list):
        for item in rag:
            if not isinstance(item, dict):
                continue
            sid = item.get("source_id") or item.get("doc_id")
            if sid is not None and str(sid).strip():
                allowed_ids.append(str(sid).strip())
        # de-dupe preserve order
        seen: set[str] = set()
        allowed_ids = [x for x in allowed_ids if not (x in seen or seen.add(x))]

    user_block = (
        f"User prompt:\n{state.get('prompt', '')}\n\nALLOWED_SOURCE_IDS:\n{json.dumps(allowed_ids)}\n\n"
        f"Retrieved source rows (citations):\n{json.dumps(rag or [], default=str)[:24_000]}\n\n"
        f"Assistant synthesis:\n{synthesis[:24_000]}\n"
    )
    raw = chat_completion(
        get_model_for_mode(),
        [
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        temperature=0.1,
    )
    brief: ResearchBrief | None = None
    try:
        brief = parse_brief_from_llm(raw or "")
    except Exception as exc:
        logger.warning("ResearchBrief parse failed: %s", exc)
        return {}

    merged_profile_qs = profiling_questions_for_workflow(brief, state.get("trading_profile"))
    strategy_name: str | None = None
    symbols: list[str] | None = None
    strategy_params: dict[str, Any] | None = None

    if _extract_enabled():
        if brief.suggested_catalog_strategies and brief.suggested_symbols:
            strategy_name = str(brief.suggested_catalog_strategies[0])
            symbols = [str(s) for s in brief.suggested_symbols]
            strategy_params = _coerce_strategy_params(brief.suggested_strategy_params) or None
        else:
            legacy = _legacy_json_extract_after_brief(
                user_prompt=str(state.get("prompt") or ""),
                synthesis=synthesis,
                brief=brief,
            )
            if legacy:
                strategy_name = str(legacy.get("strategy_name", "")) or None
                raw_syms = legacy.get("symbols")
                symbols = [str(s) for s in raw_syms] if isinstance(raw_syms, list) else None
                raw_sp = legacy.get("strategy_params")
                strategy_params = raw_sp if isinstance(raw_sp, dict) else None

    out = research_brief_graph_patch(
        brief,
        merged_profile_qs,
        strategy_name=strategy_name,
        symbols=symbols,
        strategy_params=strategy_params,
    )

    cb = _resolve_stream_callback(state, config)
    if cb is not None and callable(cb):
        ev = TraceEventV1(
            type="graph_update",
            workflow_id=state.get("workflow_id"),
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            payload={
                "research_brief": out["research_brief"],
                "profiling_questions": merged_profile_qs,
            },
        )
        cb("trace", ev.model_dump())

    return out
