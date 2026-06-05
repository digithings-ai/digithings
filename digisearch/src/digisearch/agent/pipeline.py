"""LangGraph (optional): plan → retrieve → aggregate for one research turn."""

from __future__ import annotations

import logging
from typing import Any

from digisearch.agent.citations import rag_sources_from_hits
from digisearch.agent.pipeline_models import (
    ResearchTurnOutput,
    ResearchTurnState,
    ResearchTurnTraceStep,
)
from digisearch.core.models import Query
from digisearch.core.workspace_filter import build_query_filters
from digisearch.core.standard_hits import normalize_query_hit
from digisearch.search._stub import query_index

logger = logging.getLogger(__name__)

# Query/index failures surfaced on the graph state.
_RETRIEVE_STEP_ERRORS = (ValueError, RuntimeError, ImportError, OSError, TypeError)


def _retrieve_step_failure(detail: str) -> dict[str, Any]:
    return {
        "error": detail,
        "trace": [
            ResearchTurnTraceStep(
                step="retrieve", status="failed", service="digisearch", detail=detail
            ).model_dump(mode="json")
        ],
    }


try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - optional digisearch[agent]
    START = END = StateGraph = None  # type: ignore[misc, assignment]


def node_plan(state: ResearchTurnState) -> dict[str, Any]:
    q = (state.user_message or "").strip()
    if not q:
        err = "user_message required"
        return {
            "error": err,
            "trace": [ResearchTurnTraceStep(step="plan", status="failed", detail=err)],
        }
    return {"trace": [ResearchTurnTraceStep(step="plan", status="ok", service="digisearch")]}


def node_retrieve(state: ResearchTurnState) -> dict[str, Any]:
    if state.error:
        return {}
    try:
        q = Query(
            text=str(state.user_message).strip(),
            top_k=int(state.top_k or 10),
            mode=str(state.mode or "hybrid"),
            filters=build_query_filters(
                filter_raw=state.filter,
                filters_struct=state.filters,
            ),
        )
        idx = str(state.index_name or "default")
        response = query_index(q, index_name=idx)
        rows = [normalize_query_hit(r, content_preview_max=500) for r in response.results]
        total = response.total_count if response.total_count is not None else len(rows)
        return {
            "results": rows,
            "total": total,
            "backend": response.backend,
            "trace": [
                ResearchTurnTraceStep(
                    step="retrieve",
                    status="ok",
                    service="digisearch",
                    total=total,
                )
            ],
        }
    except _RETRIEVE_STEP_ERRORS as e:
        logger.debug("research turn retrieve failed: %s", e)
        return _retrieve_step_failure(str(e))


def node_aggregate(state: ResearchTurnState) -> dict[str, Any]:
    if state.error:
        return {}
    results = state.results or []
    rag = rag_sources_from_hits(results)
    lines: list[str] = []
    for i, r in enumerate(results[:12], start=1):
        content = str(r.get("content") or "").strip()
        if len(content) > 320:
            content = content[:319].rstrip() + "…"
        doc = r.get("doc_id", "")
        lines.append(f"[{i}] doc_id={doc}\n{content}")
    formatted = "\n\n".join(lines) if lines else ""
    return {
        "rag_sources": rag,
        "formatted_context": formatted,
        "trace": [ResearchTurnTraceStep(step="aggregate", status="ok", service="digisearch")],
    }


def _route_after_plan(state: ResearchTurnState) -> str:
    return END if state.error else "retrieve"


def _route_after_retrieve(state: ResearchTurnState) -> str:
    return END if state.error else "aggregate"


def _build_graph() -> Any:
    if StateGraph is None:  # pragma: no cover
        raise ImportError("Install digisearch[agent] (langgraph) for the research-turn graph.")
    g: StateGraph[ResearchTurnState] = StateGraph(ResearchTurnState)
    g.add_node("plan", node_plan)
    g.add_node("retrieve", node_retrieve)
    g.add_node("aggregate", node_aggregate)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", _route_after_plan, {"retrieve": "retrieve", END: END})
    g.add_conditional_edges("retrieve", _route_after_retrieve, {"aggregate": "aggregate", END: END})
    g.add_edge("aggregate", END)
    return g.compile()


def _state_from_initial(initial: dict[str, Any]) -> ResearchTurnState:
    return ResearchTurnState(
        user_message=str(initial["user_message"]),
        index_name=str(initial.get("index_name") or "default"),
        top_k=int(initial.get("top_k") or 10),
        mode=str(initial.get("mode") or "hybrid"),
        filter=initial.get("filter"),
        filters=initial.get("filters"),
        session_id=initial.get("session_id"),
        service="digisearch",
        trace=[],
    )


def _output_from_state(out: ResearchTurnState | dict[str, Any]) -> ResearchTurnOutput:
    if isinstance(out, ResearchTurnState):
        state = out
    else:
        state = ResearchTurnState.model_validate(out)
    return ResearchTurnOutput(
        service="digisearch",
        error=state.error,
        trace=list(state.trace or []),
        query=state.user_message,
        index_name=state.index_name,
        total=state.total,
        backend=state.backend,
        results=list(state.results or []),
        rag_sources=list(state.rag_sources or []),
        formatted_context=state.formatted_context or "",
    )


def run_research_turn(initial: dict[str, Any]) -> dict[str, Any]:
    """Execute one research turn; returns JSON suitable for HTTP/MCP and hub connectors."""
    if StateGraph is None:
        raise ImportError("digisearch[agent] is not installed (requires langgraph).")
    graph = _build_graph()
    out = graph.invoke(_state_from_initial(initial))
    return _output_from_state(out).model_dump(mode="json")
