"""digigraph product graphs — scheduled digiquant research/portfolio runs (#3415).

Platform rule: product paths are digigraph → digillm (via digigraph.llm_client when
LLM nodes exist). Domain logic stays in digiquant; digigraph never imports
digiquant Python packages — vertical calls use ``invoke_digiquant_tool``.

First slice: ``research-portfolio-chain`` compiles both sub-graphs through the
digiquant orchestrator dry path. Full apply cutover is follow-up work on the
same issues (#3415 / #3424).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Literal  # score:allow untyped any — digiquant hub JSON bodies

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, field_validator

from digigraph.vertical_orchestrator.digiquant_hub import invoke_digiquant_tool

ProductGraphName = Literal["research-portfolio-chain"]


class ProductGraphSpec(BaseModel):
    """Registered product graph metadata."""

    model_config = ConfigDict(extra="forbid")

    name: ProductGraphName
    description: str
    digiquant_tool: str
    default_dry_run: bool = True


PRODUCT_GRAPH_SPECS: dict[str, ProductGraphSpec] = {
    "research-portfolio-chain": ProductGraphSpec(
        name="research-portfolio-chain",
        description=(
            "Daily digiquant research → portfolio chain as a digigraph product "
            "graph. First slice: dry compile via digiquant orchestrator."
        ),
        digiquant_tool="digiquant_compile_research_portfolio",
        default_dry_run=True,
    ),
}


class ProductGraphRunState(BaseModel):
    """LangGraph state for a product-graph run."""

    model_config = ConfigDict(extra="forbid")

    graph_name: ProductGraphName = "research-portfolio-chain"
    run_date: date
    cadence: str = "daily"
    refresh_scope: str = "none"
    watchlist: list[str] = Field(default_factory=list)
    dry_run: bool = True
    digiquant_base_url: str | None = None
    digi_bearer: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    digiquant_result: dict[str, Any] | None = None
    status: Literal["pending", "ok", "error"] = "pending"
    error: str | None = None

    @field_validator("watchlist", mode="before")
    @classmethod
    def _normalize_watchlist(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [p.strip().upper() for p in value.split(",") if p.strip()]
            return parts
        if isinstance(value, (list, tuple)):
            return [str(x).strip().upper() for x in value if str(x).strip()]
        return []


class ProductGraphRunRequest(BaseModel):
    """HTTP body for ``POST /v1/product_graphs/{name}/runs``."""

    model_config = ConfigDict(extra="forbid")

    run_date: date | None = None
    cadence: str = "daily"
    refresh_scope: str = "none"
    watchlist: list[str] = Field(default_factory=list)
    dry_run: bool = True


DigiquantInvoker = Callable[..., dict[str, Any]]


def list_product_graphs() -> list[ProductGraphSpec]:
    """Return registered product graphs (stable order)."""
    return [PRODUCT_GRAPH_SPECS[k] for k in sorted(PRODUCT_GRAPH_SPECS)]


def get_product_graph_spec(name: str) -> ProductGraphSpec | None:
    return PRODUCT_GRAPH_SPECS.get(name)


def _resolve_key(state: ProductGraphRunState) -> dict[str, Any]:
    key = f"{state.graph_name}:{state.run_date.isoformat()}:{state.cadence}:{state.refresh_scope}"
    return {"idempotency_key": key, "status": "pending", "error": None}


def _invoke_digiquant(
    state: ProductGraphRunState,
    *,
    invoker: DigiquantInvoker,
    digiquant_tool: str,
) -> dict[str, Any]:
    if not state.dry_run:
        return {
            "status": "error",
            "error": (
                "full apply is not enabled on digigraph product graphs yet; "
                "pass dry_run=true (compile-only) or use digiquant.portfolio.chain"
            ),
        }
    base = (state.digiquant_base_url or "").strip()
    if not base:
        return {
            "status": "error",
            "error": "DIGIQUANT_URL / digiquant_base_url required for product graph invoke",
        }
    body = invoker(
        base,
        digiquant_tool,
        {
            "run_date": state.run_date.isoformat(),
            "cadence": state.cadence,
            "refresh_scope": state.refresh_scope,
            "watchlist": state.watchlist,
            "graph_name": state.graph_name,
        },
        bearer_token=state.digi_bearer,
        request_id=state.request_id,
    )
    if not isinstance(body, dict) or not body.get("ok"):
        err = None
        if isinstance(body, dict):
            err = body.get("error")
        return {
            "status": "error",
            "error": str(err or "digiquant invoke failed"),
            "digiquant_result": body if isinstance(body, dict) else None,
        }
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    return {
        "status": "ok",
        "error": None,
        "digiquant_result": data if isinstance(data, dict) else {"raw": data},
        "idempotency_key": (
            data.get("idempotency_key")
            if isinstance(data, dict) and data.get("idempotency_key")
            else state.idempotency_key
        ),
    }


def build_research_portfolio_product_graph(
    *,
    invoker: DigiquantInvoker | None = None,
):
    """Compile the research-portfolio-chain product graph.

    ``invoker`` defaults to :func:`invoke_digiquant_tool` (HTTP). Tests inject a
    stub so the graph can be walked without a live digiquant.
    """
    spec = PRODUCT_GRAPH_SPECS["research-portfolio-chain"]
    call = invoker or invoke_digiquant_tool

    def resolve_key(state: ProductGraphRunState) -> dict[str, Any]:
        return _resolve_key(state)

    def invoke_vertical(state: ProductGraphRunState) -> dict[str, Any]:
        return _invoke_digiquant(state, invoker=call, digiquant_tool=spec.digiquant_tool)

    g: StateGraph[ProductGraphRunState] = StateGraph(ProductGraphRunState)
    g.add_node("resolve_key", resolve_key)
    g.add_node("invoke_digiquant", invoke_vertical)
    g.add_edge(START, "resolve_key")
    g.add_edge("resolve_key", "invoke_digiquant")
    g.add_edge("invoke_digiquant", END)
    return g.compile()


def run_product_graph(
    name: str,
    request: ProductGraphRunRequest,
    *,
    digiquant_base_url: str | None,
    digi_bearer: str | None = None,
    request_id: str | None = None,
    invoker: DigiquantInvoker | None = None,
) -> ProductGraphRunState:
    """Invoke a registered product graph once."""
    spec = get_product_graph_spec(name)
    fallback_date = request.run_date or datetime.now(timezone.utc).date()
    if spec is None:
        return ProductGraphRunState(
            graph_name="research-portfolio-chain",
            run_date=fallback_date,
            status="error",
            error=f"unknown product graph: {name}",
        )
    if name != "research-portfolio-chain":
        return ProductGraphRunState(
            graph_name="research-portfolio-chain",
            run_date=fallback_date,
            status="error",
            error=f"product graph not implemented yet: {name}",
        )

    run_date = request.run_date or datetime.now(timezone.utc).date()
    initial = ProductGraphRunState(
        graph_name=spec.name,
        run_date=run_date,
        cadence=request.cadence,
        refresh_scope=request.refresh_scope,
        watchlist=list(request.watchlist),
        dry_run=request.dry_run if request.dry_run is not None else spec.default_dry_run,
        digiquant_base_url=digiquant_base_url,
        digi_bearer=digi_bearer,
        request_id=request_id,
    )
    graph = build_research_portfolio_product_graph(invoker=invoker)
    result = graph.invoke(initial)
    if isinstance(result, ProductGraphRunState):
        return result
    return ProductGraphRunState.model_validate(result)
