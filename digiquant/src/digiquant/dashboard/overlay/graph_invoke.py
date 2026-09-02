"""One-graph overlay invoke (T4).

Stamps ``workspace_id`` + ``profile_config_version_id`` on the research pin seam
and calls the existing research→portfolio compose with ``manage_usage=False`` so
``overlay_usage_scope`` owns WP1 capture. House/system ids are refused.
This module does not import ``byok`` / digillm at module level.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from uuid import UUID

from digiquant.research.state import ResearchConfigBundle
from digiquant.dashboard.overlay.models import OverlayError
from digiquant.dashboard.tenancy import house_workspace_id, system_workspace_id

OverlayInvoke = Callable[..., object]


def overlay_config_bundle(
    *,
    workspace_id: UUID,
    profile_version_id: UUID,
    watchlist: tuple[str, ...] = (),
) -> ResearchConfigBundle:
    """Pin seam for overlay: workspace + exact profile version, never house default."""
    if workspace_id in {house_workspace_id(), system_workspace_id()}:
        raise OverlayError("house_workspace", "overlay graph refuses the house/system workspace id")
    return ResearchConfigBundle(
        watchlist=list(watchlist),
        workspace_id=str(workspace_id),
        profile_config_version_id=str(profile_version_id),
    )


def build_overlay_chain(
    *,
    workspace_id: UUID,
    profile_version_id: UUID,
    invoke: OverlayInvoke | None = None,
) -> OverlayInvoke:
    """Return the invoke callable ``invoke_overlay_chain`` expects.

    ``invoke`` is injectable so unit tests never compile the dashboard graph.
    Production uses :func:`_invoke_dashboard_graph` (lazy portfolio import).
    """
    overlay_config_bundle(workspace_id=workspace_id, profile_version_id=profile_version_id)

    def chain(
        *,
        workspace_id: UUID,
        run_date: date,
        requested_version_id: UUID,
    ) -> None:
        runner = invoke if invoke is not None else _invoke_dashboard_graph
        runner(
            workspace_id=workspace_id,
            run_date=run_date,
            requested_version_id=requested_version_id,
            manage_usage=False,
        )

    return chain


def _overlay_chain_deps(
    *,
    client: object,
    workspace_id: UUID,
    requested_version_id: UUID,
) -> object:
    """Build research→portfolio deps with the overlay pin on the config loader."""
    # Dependency-isolation: portfolio/research pull digillm; cron unit tests never call this.
    from digiquant.research.graph import ResearchGraphDeps
    from digiquant.research.phases.preflight import PreflightDeps, PreflightReflectDeps
    from digiquant.research.phases.publish_phase import PublishDeps
    from digiquant.research.phases.triage_phase import TriageDeps
    from digiquant.portfolio.chain import ChainDeps
    from digiquant.portfolio.graph import PortfolioGraphDeps, ThesisGraphDeps
    from digiquant.portfolio.phases.h9_commit_run import CommitRunDeps
    from digiquant.portfolio.phases.phase7e_risk_sizing import RiskSizingDeps

    def config_loader() -> ResearchConfigBundle:
        return overlay_config_bundle(
            workspace_id=workspace_id,
            profile_version_id=requested_version_id,
        )

    research = ResearchGraphDeps(
        preflight=PreflightDeps(client=client, config_loader=config_loader),
        publish=None,
        triage=TriageDeps(client=client),
        preflight_reflect=PreflightReflectDeps(client=client),
    )
    portfolio = PortfolioGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    return ChainDeps(
        research=research,
        portfolio=portfolio,
        publish=PublishDeps(client=client),
        diagnostics=None,
    )


_SUPABASE_READ_ERRORS = (OSError, RuntimeError, ValueError, TypeError, KeyError)


def _overlay_held(client: object, run_date: date, workspace_id: UUID) -> tuple[str, ...]:
    from digiquant.research.supabase_io import load_prior_book
    from digiquant.portfolio.candidates import holdings_from_prior_book

    try:
        prior = load_prior_book(client, run_date, workspace_id=str(workspace_id))
    except _SUPABASE_READ_ERRORS:
        return ()
    return tuple(holdings_from_prior_book(prior))


def _invoke_dashboard_graph(
    *,
    workspace_id: UUID,
    run_date: date,
    requested_version_id: UUID,
    manage_usage: bool = False,
) -> None:
    """Production graph invoke. Lazy-imports portfolio so cron tests stay digillm-free."""
    from digiquant.research.graph import ResearchInput
    from digiquant.research.supabase_io import SupabaseConfig, build_client
    from digiquant.portfolio.chain import run_research_then_portfolio

    overlay_config_bundle(workspace_id=workspace_id, profile_version_id=requested_version_id)
    client = build_client(SupabaseConfig.from_env())
    deps = _overlay_chain_deps(
        client=client,
        workspace_id=workspace_id,
        requested_version_id=requested_version_id,
    )
    run_research_then_portfolio(
        research_input=ResearchInput(run_date=run_date, watchlist=()),
        deps=deps,
        portfolio_held=_overlay_held(client, run_date, workspace_id),
        manage_usage=manage_usage,
    )


__all__ = [
    "build_overlay_chain",
    "overlay_config_bundle",
]
