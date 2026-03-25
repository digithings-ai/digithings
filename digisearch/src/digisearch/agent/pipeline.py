"""LangGraph (optional): plan → retrieve → aggregate for one research turn."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict

from digisearch.agent.citations import rag_sources_from_hits
from digisearch.core.filter_validator import validate_odata_filter
from digisearch.core.models import Query
from digisearch.core.standard_hits import normalize_query_hit
from digisearch.search._stub import query_index

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - optional digisearch[agent]
    START = END = StateGraph = None  # type: ignore[misc, assignment]


class ResearchTurnState(TypedDict, total=False):
    user_message: str
    index_name: str
    top_k: int
    mode: str
    filter: str | None
    filters: list[dict[str, Any]] | None
    session_id: str | None
    service: str
    trace: Annotated[list[dict[str, Any]], add]
    results: list[dict[str, Any]]
    total: int
    rag_sources: list[dict[str, Any]]
    formatted_context: str
    error: str | None


def _build_query_filters(
    filter_raw: str | None,
    filters_struct: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if filter_raw and filter_raw.strip():
        filters["odata"] = validate_odata_filter(filter_raw.strip())
    if filters_struct:
        filters["structured"] = filters_struct
    return filters


def node_plan(state: ResearchTurnState) -> dict[str, Any]:
    q = (state.get("user_message") or "").strip()
    if not q:
        err = "user_message required"
        return {"error": err, "trace": [{"step": "plan", "status": "failed", "detail": err}]}
    return {"trace": [{"step": "plan", "status": "ok", "service": "digisearch"}]}


def node_retrieve(state: ResearchTurnState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    try:
        q = Query(
            text=str(state["user_message"]).strip(),
            top_k=int(state.get("top_k") or 10),
            mode=str(state.get("mode") or "hybrid"),
            filters=_build_query_filters(state.get("filter"), state.get("filters")),
        )
        idx = str(state.get("index_name") or "default")
        response = query_index(q, index_name=idx)
        rows = [normalize_query_hit(r, content_preview_max=500) for r in response.results]
        total = response.total_count if response.total_count is not None else len(rows)
        return {
            "results": rows,
            "total": total,
            "backend": response.backend,
            "trace": [{"step": "retrieve", "status": "ok", "service": "digisearch", "total": total}],
        }
    except Exception as e:
        msg = str(e)
        return {
            "error": msg,
            "trace": [{"step": "retrieve", "status": "failed", "service": "digisearch", "detail": msg}],
        }


def node_aggregate(state: ResearchTurnState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    results = state.get("results") or []
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
        "trace": [{"step": "aggregate", "status": "ok", "service": "digisearch"}],
    }


def _route_after_plan(state: ResearchTurnState) -> str:
    return END if state.get("error") else "retrieve"


def _route_after_retrieve(state: ResearchTurnState) -> str:
    return END if state.get("error") else "aggregate"


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


def run_research_turn(initial: dict[str, Any]) -> dict[str, Any]:
    """Execute one research turn; returns JSON suitable for HTTP/MCP and hub connectors."""
    if StateGraph is None:
        raise ImportError("digisearch[agent] is not installed (requires langgraph).")
    graph = _build_graph()
    state_in: ResearchTurnState = {
        "user_message": str(initial["user_message"]),
        "index_name": str(initial.get("index_name") or "default"),
        "top_k": int(initial.get("top_k") or 10),
        "mode": str(initial.get("mode") or "hybrid"),
        "filter": initial.get("filter"),
        "filters": initial.get("filters"),
        "session_id": initial.get("session_id"),
        "service": "digisearch",
        "trace": [],
    }
    out = graph.invoke(state_in)
    return {
        "service": "digisearch",
        "error": out.get("error"),
        "trace": list(out.get("trace") or []),
        "query": out.get("user_message"),
        "index_name": out.get("index_name"),
        "total": out.get("total", 0),
        "backend": out.get("backend"),
        "results": out.get("results") or [],
        "rag_sources": out.get("rag_sources") or [],
        "formatted_context": out.get("formatted_context") or "",
    }
