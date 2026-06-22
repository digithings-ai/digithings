"""Pre-flight: config load, prior context, data-layer probe (no LLM).

See ``atlas/docs/agentic/ARCHITECTURE.md`` Pre-Flight Protocol.
``preflight_reflect`` resolves due ``decision_log`` rows (Phase B #432).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

import yaml

from digiquant.data.onchain.hyperdash import get_onchain_cohort_positioning
from digiquant.olympus.atlas.data.queries import get_fed_rate_probabilities, get_market_context
from digiquant.olympus.atlas.decision_log import (
    ReflectorOutput,
    fetch_recent_lessons,
    resolve_pending,
)
from digiquant.olympus.atlas.sectors_config import load_sectors
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_active_theses_rows,
    load_prior_analyst_summaries,
    load_prior_book,
    load_prior_context,
    load_portfolio_performance_snapshot,
    prior_book_current_weights,
    query_institutional_absence_streak,
    query_macro_series_freshness,
    query_price_technicals_freshness,
    upsert_onchain_cohort_positioning,
)
from digiquant.olympus.hermes.candidates import holdings_from_prior_book

# decision_log may be empty or not yet migrated — do not fail the rest of preflight.
_SUPABASE_READ_ERRORS = (OSError, RuntimeError, ValueError, TypeError, KeyError)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreflightDeps:
    """Wiring deps for the preflight node (injected client + config_loader)."""

    client: SupabaseClient
    config_loader: Callable[[], AtlasConfigBundle]
    # Staleness threshold for price_technicals: if the latest date is older
    # than run_date - this many days, we flag a fallback in DataLayerSnapshot.
    price_staleness_days: int = 3
    # Day window for the institutional-absence probe feeding the Phase 2
    # circuit-breaker (#928). 30 days covers a baseline + a month of deltas
    # with slack; matches the documents-read window in ``load_prior_context``.
    institutional_absence_lookback_days: int = 30


# Broad-market ETFs (+ BTC/ETH) always present in the injected market context.
# Sector ETFs are appended from config/sectors.yaml at preflight time.
_CORE_MARKET_TICKERS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "IEF",
    "HYG",
    "LQD",
    "GLD",
    "SLV",
    "USO",
    "UUP",
    "EFA",
    "EEM",
    "FXI",
    "BTC-USD",
    "ETH-USD",
)


def _market_context_tickers() -> list[str]:
    """Core ETF set + the headline ETF of each configured sector (deduped)."""
    tickers = list(_CORE_MARKET_TICKERS)
    try:
        for sector in load_sectors():
            etfs = getattr(sector, "etfs", None) or []
            if etfs and etfs[0] not in tickers:
                tickers.append(etfs[0])
    except (OSError, ValueError, yaml.YAMLError):
        # sectors.yaml missing/malformed → core set still ships.
        pass
    return tickers


def _refresh_on_demand_enabled() -> bool:
    """``ATLAS_REFRESH_ON_DEMAND`` — opt in to the in-graph technicals recompute (off by
    default; the CI pre-baseline step is the primary freshness mechanism)."""
    return os.environ.get("ATLAS_REFRESH_ON_DEMAND", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _refresh_stale_technicals(
    deps: PreflightDeps, run_date: date, config: AtlasConfigBundle
) -> bool:
    """Recompute technicals from ``price_history`` (network-free) to clear staleness.

    Opt-in via ``ATLAS_REFRESH_ON_DEMAND``; fail-soft → ``False`` (keep the stale data and
    the ``"scripts"`` fallback signal). Returns True only when rows were actually upserted.
    """
    if not _refresh_on_demand_enabled():
        return False
    tickers = list(config.watchlist)
    if not tickers:
        return False
    try:
        from digiquant.data.prices.refresh import recompute_technicals_from_history

        result = recompute_technicals_from_history(
            client=deps.client, tickers=tickers, as_of=run_date
        )
        return result.rows_upserted > 0
    except Exception as exc:  # noqa: BLE001 — refresh is best-effort; never block preflight
        logger.warning(
            "preflight: on-demand technicals refresh failed (%s); using stale data",
            exc,
            exc_info=True,
        )
        return False


def _data_layer_snapshot(
    deps: PreflightDeps, run_date: date, config: AtlasConfigBundle
) -> DataLayerSnapshot:
    """Probe price_technicals + macro_series freshness; empty tables are valid."""
    latest_tech, ticker_count = query_price_technicals_freshness(client=deps.client)
    macro_latest = query_macro_series_freshness(client=deps.client)

    fallback: str = "supabase"
    if latest_tech is None:
        fallback = "none"
    else:
        # Stale data → caller should prefer scripts/mcp fallback. This decision
        # lives with the phase-3 macro node today, but we surface it here so
        # triage (commit 8) can consider it.
        stale_cutoff = run_date - _days(deps.price_staleness_days)
        if latest_tech < stale_cutoff:
            fallback = "scripts"
            # On-demand refresh (opt-in, network-free): recompute technicals from
            # price_history so the research phases read current values. Re-probe; if the
            # table is now fresh, clear the fallback signal (#726, 1F).
            if _refresh_stale_technicals(deps, run_date, config):
                latest_tech, ticker_count = query_price_technicals_freshness(client=deps.client)
                if latest_tech is not None and latest_tech >= stale_cutoff:
                    fallback = "supabase"

    # Deterministic market values for every phase's shared context (#694).
    # Fail-soft: research must proceed (ungrounded) on a data-layer hiccup.
    market_context: dict[str, Any] = {}
    try:
        market_context = get_market_context(
            client=deps.client,
            tickers=_market_context_tickers(),
            series_ids=list(config.macro_series),
            run_date=run_date,
        )
    except _SUPABASE_READ_ERRORS as exc:
        logger.warning("market_context unavailable (%s); phases run without injected values", exc)

    # Fed rate-decision odds from prediction markets. Injected into market_context so
    # phase6_consolidate can read it for the bias-row fed_odds slot. Fail-soft to None —
    # a Kalshi/Polymarket outage must never block a run.
    try:
        fed_odds = get_fed_rate_probabilities(client=deps.client, run_date=run_date) or None
    except _SUPABASE_READ_ERRORS as exc:
        logger.warning("fed_odds unavailable (%s); fed_odds slot will be None this run", exc)
        fed_odds = None
    if fed_odds is not None:
        market_context["fed_odds"] = fed_odds

    # On-chain cohort positioning (smart-money vs rekt divergence) from Hyperdash (#801). The
    # compact summary is injected into market_context so the alt-onchain-positioning segment + the
    # phase6 bias row can read it (mirrors fed_odds); the per-market frame is persisted for
    # backtest. Best-effort end to end — a Hyperdash outage/shape-drift must never block a run.
    try:
        onchain = get_onchain_cohort_positioning()
    except Exception as exc:  # noqa: BLE001 — provider is fail-soft, but never let it crash preflight
        logger.warning("onchain positioning unavailable (%s); slot will be None this run", exc)
        onchain = None
    if onchain is not None and onchain.error is None and onchain.has_data:
        # Inject the signal even if persistence fails: the segment + bias row only need the compact
        # summary, so the overlay is fully usable before migration 042 lands.
        market_context["onchain_positioning"] = onchain.compact_summary()
        try:
            upsert_onchain_cohort_positioning(
                client=deps.client, rows=onchain.to_rows(run_date.isoformat())
            )
        except Exception as exc:  # noqa: BLE001 — persistence is best-effort; a missing table
            # (pre-migration window) or any postgrest/network error must never block the run.
            logger.warning("onchain positioning persist failed (%s); continuing", exc)

    # Institutional ingest/publish probe for the Phase 2 circuit-breaker (#928).
    # Fail-soft: a probe error must never trip the breaker — keep the
    # institutional nodes running (streak 0, available True) so a transient read
    # error doesn't silently drop paid-but-needed grounding.
    try:
        inst_absence_streak = query_institutional_absence_streak(
            client=deps.client,
            run_date=run_date,
            lookback_days=deps.institutional_absence_lookback_days,
        )
    except _SUPABASE_READ_ERRORS as exc:
        logger.warning("institutional-absence probe failed (%s); breaker stays open this run", exc)
        inst_absence_streak = 0

    # ── Data-layer starvation flags (#946) ──────────────────────────────
    # (a) Basket completeness: expected tickers with zero rows in price_technicals.
    expected_tickers = set(_market_context_tickers())
    present_tickers: set[str] = set()
    mc_technicals = market_context.get("price_technicals")
    if isinstance(mc_technicals, dict):
        present_tickers = set(mc_technicals.keys())
    price_basket_gap = sorted(expected_tickers - present_tickers)
    if price_basket_gap:
        logger.warning(
            "preflight: price_technicals basket gap — %d/%d expected tickers missing: %s",
            len(price_basket_gap),
            len(expected_tickers),
            price_basket_gap[:10],  # truncate for log readability
        )

    # (b)+(c) Freshness: >2 business days before run_date → stale.
    stale_price = latest_tech is None or _business_days_between(latest_tech, run_date) > 2
    stale_macro = macro_latest is None or _business_days_between(macro_latest, run_date) > 2
    if stale_price:
        logger.warning(
            "preflight: price_technicals stale (latest=%s, run_date=%s)",
            latest_tech,
            run_date,
        )
    if stale_macro:
        logger.warning(
            "preflight: macro_series stale (latest=%s, run_date=%s)",
            macro_latest,
            run_date,
        )

    return DataLayerSnapshot(
        price_technicals_latest=latest_tech,
        price_technicals_ticker_count=ticker_count,
        macro_series_latest=macro_latest,
        fallback_used=fallback,  # type: ignore[arg-type]
        market_context=market_context,
        institutional_data_available=inst_absence_streak == 0,
        institutional_absence_streak=inst_absence_streak,
        price_basket_gap=price_basket_gap,
        stale_price=stale_price,
        stale_macro=stale_macro,
    )


def _days(n: int):
    """Return a timedelta(days=n). Import deferred to keep module-top small."""
    from datetime import timedelta

    return timedelta(days=n)


def _business_days_between(earlier: date, later: date) -> int:
    """Count business days (Mon–Fri) strictly between ``earlier`` and ``later``.

    Returns 0 when ``later <= earlier``. Used for the >2-business-day staleness
    check (#946) — weekends / holidays (not tracked) are excluded so a Monday
    run with a Friday latest observation reads as 0 gap, not 2.
    """
    if later <= earlier:
        return 0
    from datetime import timedelta

    count = 0
    current = earlier + timedelta(days=1)
    while current <= later:
        # Monday=0 … Friday=4 are weekdays.
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _hydrate_config(
    client: SupabaseClient,
    config: AtlasConfigBundle,
    run_date: date,
) -> tuple[AtlasConfigBundle, list[dict[str, Any]]]:
    """Merge portfolio constraints + materialized prior book into config preferences."""
    from digiquant.olympus.atlas.dashboard_digest import portfolio_preferences_static
    from digiquant.olympus.atlas.graph import _atlas_config_root

    try:
        prior_book = load_prior_book(client, run_date)
    except _SUPABASE_READ_ERRORS:
        prior_book = []

    preferences = {
        **portfolio_preferences_static(_atlas_config_root() / "portfolio.json"),
        **dict(config.preferences),
    }
    current_weights = prior_book_current_weights(prior_book)
    if current_weights:
        preferences["current_weights"] = current_weights

    hydrated = AtlasConfigBundle(
        watchlist=list(config.watchlist),
        investment_profile=dict(config.investment_profile),
        hedge_funds=list(config.hedge_funds),
        preferences=preferences,
        macro_series=list(config.macro_series),
    )
    return hydrated, prior_book


def build_preflight_node(deps: PreflightDeps) -> Callable[[AtlasResearchState], dict]:
    """Return the LangGraph preflight node bound to ``deps``."""

    def preflight(state: AtlasResearchState) -> dict:
        # Legacy delta runs required baseline_date for carry provenance. Daily
        # cadence resolves priors per-artifact via prior_published (spec §5.1).
        if state.cadence != "daily" and state.run_type == "delta" and state.baseline_date is None:
            raise ValueError("delta run requires baseline_date to be set on AtlasResearchState")

        config = deps.config_loader()
        config, prior_book = _hydrate_config(deps.client, config, state.run_date)
        prior_context = load_prior_context(client=deps.client, run_date=state.run_date)
        data_layer = _data_layer_snapshot(deps, state.run_date, config)

        # Hydrate ``decision_lessons`` from ``decision_log`` so the PM (Phase 7D)
        # sees prior reflections this run. The fetch is bounded:
        # - up to 5 same-ticker rows per watchlist member,
        # - up to 3 cross-ticker rows.
        # An empty list on first run is fine — the PM skill ignores it.
        watchlist = tuple(config.watchlist) if config.watchlist else ()
        try:
            lessons = fetch_recent_lessons(
                client=deps.client,
                run_date=state.run_date,
                watchlist=watchlist,
            )
        except _SUPABASE_READ_ERRORS:
            lessons = []

        held_tickers = holdings_from_prior_book(prior_book)
        try:
            prior_analyst = load_prior_analyst_summaries(deps.client, state.run_date, held_tickers)
        except _SUPABASE_READ_ERRORS:
            prior_analyst = {}
        try:
            active_theses = load_active_theses_rows(deps.client, state.run_date)
        except _SUPABASE_READ_ERRORS:
            active_theses = []
        try:
            portfolio_performance = load_portfolio_performance_snapshot(deps.client, state.run_date)
        except _SUPABASE_READ_ERRORS:
            portfolio_performance = {}

        prior_context = PriorContext(
            last_snapshots=prior_context.last_snapshots,
            latest_segments=prior_context.latest_segments,
            active_theses=active_theses,
            decision_lessons=lessons,
            prior_book=prior_book,
            prior_analyst_by_ticker=prior_analyst,
            portfolio_performance=portfolio_performance,
        )

        return {
            "config": config,
            "prior_context": prior_context,
            "data_layer": data_layer,
        }

    return preflight


@dataclass(frozen=True)
class PreflightReflectDeps:
    """Wiring deps for ``preflight_reflect`` (optional stub ``reflector``)."""

    client: SupabaseClient
    reflector: Callable[[dict[str, Any]], ReflectorOutput] | None = None


def build_preflight_reflect_node(
    deps: PreflightReflectDeps,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return the Phase B reflect node bound to ``deps``."""

    def reflect(state: AtlasResearchState) -> dict[str, Any]:
        resolve_pending(
            client=deps.client,
            run_date=state.run_date,
            reflector=deps.reflector,
        )
        return {}

    return reflect
