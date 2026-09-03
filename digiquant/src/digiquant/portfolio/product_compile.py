"""Compile-only research → portfolio topology for DigiGraph product graphs (#3415).

This is the digiquant-owned dry path that digigraph invokes over
``POST /v1/orchestrator_invoke`` (no digigraph → digiquant Python import).
Full apply still goes through :func:`digiquant.portfolio.chain.run_research_then_portfolio`
until the product-graph cutover lands; this module never calls an LLM or writes
the book.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from digiquant.portfolio.graph import PortfolioGraphDeps, build_portfolio_graph
from digiquant.research.graph import ResearchGraphDeps, build_research_graph
from digiquant.research.phases.preflight import PreflightDeps


class ProductCompileGraphStatus(BaseModel):
    """Whether one sub-graph compiled cleanly."""

    model_config = ConfigDict(extra="forbid")

    name: Literal["research", "portfolio"]
    compiled: bool
    error: str | None = None


class ProductCompileResult(BaseModel):
    """Structured dry-run result for DigiGraph product-graph scaffolding."""

    model_config = ConfigDict(extra="forbid")

    dry_run: Literal[True] = True
    cadence: str
    refresh_scope: str
    run_date: date
    watchlist: list[str] = Field(default_factory=list)
    graphs: list[ProductCompileGraphStatus]
    idempotency_key: str

    def as_orchestrator_data(self) -> dict[str, Any]:
        """JSON-ready payload for ``orchestrator_invoke`` responses."""
        return self.model_dump(mode="json")


def idempotency_key_for(
    *,
    graph_name: str,
    run_date: date,
    cadence: str = "daily",
    refresh_scope: str = "none",
) -> str:
    """Stable key for scheduled product-graph runs (Wave 2 sketch)."""
    return f"{graph_name}:{run_date.isoformat()}:{cadence}:{refresh_scope}"


def compile_research_portfolio(
    *,
    run_date: date,
    cadence: str = "daily",
    refresh_scope: str = "none",
    watchlist: tuple[str, ...] | list[str] = (),
    graph_name: str = "research-portfolio-chain",
) -> ProductCompileResult:
    """Compile research + portfolio graphs without invoking nodes.

    Mirrors ``portfolio.chain`` ``--dry-run`` but returns a Pydantic model so
    DigiGraph product graphs and tests can assert topology without parsing CLI
    stdout.
    """
    wl = tuple(str(t).strip().upper() for t in watchlist if str(t).strip())
    statuses: list[ProductCompileGraphStatus] = []

    try:
        research_deps = ResearchGraphDeps(
            preflight=PreflightDeps(client=None, config_loader=None),  # type: ignore[arg-type]
        )
        build_research_graph(deps=research_deps, watchlist=wl)
        statuses.append(ProductCompileGraphStatus(name="research", compiled=True))
    except Exception as exc:  # pragma: no cover — compile failures are wiring bugs
        statuses.append(
            ProductCompileGraphStatus(name="research", compiled=False, error=repr(exc)[:500])
        )

    try:
        build_portfolio_graph(watchlist=list(wl), deps=PortfolioGraphDeps())
        statuses.append(ProductCompileGraphStatus(name="portfolio", compiled=True))
    except Exception as exc:  # pragma: no cover
        statuses.append(
            ProductCompileGraphStatus(name="portfolio", compiled=False, error=repr(exc)[:500])
        )

    return ProductCompileResult(
        cadence=cadence,
        refresh_scope=refresh_scope,
        run_date=run_date,
        watchlist=list(wl),
        graphs=statuses,
        idempotency_key=idempotency_key_for(
            graph_name=graph_name,
            run_date=run_date,
            cadence=cadence,
            refresh_scope=refresh_scope,
        ),
    )
