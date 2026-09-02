"""Pre-flight: config load, prior context, data-layer probe (no LLM).

See ``atlas/docs/agentic/ARCHITECTURE.md`` Pre-Flight Protocol.
``preflight_reflect`` resolves due ``decision_log`` rows (Phase B #432) and,
beside that path, matured typed forecast outcomes (#2676 / WP5.2) — never by
converting legacy conviction scores inside ``decision_log``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import (  # score:allow untyped any — used for heterogeneous node-update dict shape
    Any,
    Callable,
)
from uuid import UUID

import yaml

from digiquant.data.onchain.hyperdash import get_onchain_cohort_positioning
from digiquant.research.cost_liquidity_registry import (
    resolve_realized_action_cost_outcomes_from_state,
)
from digiquant.research.data.queries import get_fed_rate_probabilities, get_market_context
from digiquant.research.decision_log import (
    ReflectorOutput,
    fetch_recent_lessons,
    resolve_pending,
)
from digiquant.research.forecast_outcomes import resolve_matured_forecast_outcomes
from digiquant.research.sectors_config import load_sectors
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.research.supabase_io import (
    SupabaseClient,
    load_active_theses_rows,
    load_portfolio_performance_snapshot,
    load_prior_analyst_summaries,
    load_prior_book,
    load_prior_context,
    load_prior_deliberation_summaries,
    prior_book_current_weights,
    query_institutional_absence_streak,
    query_macro_series_freshness,
    query_price_deltas,
    query_price_technicals_freshness,
    upsert_onchain_cohort_positioning,
)
from digiquant.dashboard.envcompat import ATTEMPT, REFRESH_ON_DEMAND, env_lookup
from digiquant.portfolio.candidates import holdings_from_prior_book
from digiquant.portfolio.turnover import mark_to_market_weights
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register
from digiquant.dashboard.overlay.runner import pin_seam_config
from digiquant.dashboard.temporal import require_knowledge_cutoff_at

# decision_log may be empty or not yet migrated — do not fail the rest of preflight.
_SUPABASE_READ_ERRORS = (OSError, RuntimeError, ValueError, TypeError, KeyError)

logger = logging.getLogger(__name__)


def _is_cash_ticker(ticker: str) -> bool:
    return str(ticker).strip().upper() == "CASH"


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
    # WP12.3 (#2863): optional in-process ResearchStateStore for exact pin.
    # None → typed state_unavailable (compatibility documents stay shadow-only).
    research_state_store: Any | None = None
    # WP15.6 (#2975): optional outcome-learning maturation stack for lesson pin.
    outcome_maturation_deps: Any | None = None
    # Outer-retry attempt id (string form of OLYMPUS_ATTEMPT / DiagnosticsDeps.attempt).
    research_state_attempt_id: str | None = None


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
    return env_lookup(REFRESH_ON_DEMAND).strip().lower() in (
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
    except Exception as exc:  # refresh is best-effort; never block preflight
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
    except Exception as exc:  # provider is fail-soft, but never let it crash preflight
        logger.warning("onchain positioning unavailable (%s); slot will be None this run", exc)
        onchain = None
    if onchain is not None and onchain.error is None and onchain.has_data:
        # Inject the signal even if persistence fails: the segment + bias row only need the compact
        # summary, so the overlay is fully usable before migration 042 lands.
        market_context["onchain_positioning"] = onchain.compact_summary()
        try:
            upsert_onchain_cohort_positioning(
                client=deps.client,
                rows=onchain.to_rows(run_date.isoformat()),
                workspace_id=config.workspace_id,
            )
        except Exception as exc:  # persistence is best-effort; a missing table
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


def _profile_config_store_for_pin(client: SupabaseClient, version_id: str) -> dict[str, Any]:
    """Load one olympus_profile_config payload by exact id (fail closed if absent)."""
    try:
        response = (
            client.table("olympus_profile_config")
            .select("id,payload")
            .eq("id", version_id)
            .limit(1)
            .execute()
        )
    except _SUPABASE_READ_ERRORS:
        return {}
    rows = getattr(response, "data", None) or []
    if not rows:
        return {}
    row = rows[0]
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return {}
    return {str(row.get("id") or version_id): payload}


def _hydrate_config(
    client: SupabaseClient,
    config: AtlasConfigBundle,
    run_date: date,
) -> tuple[AtlasConfigBundle, list[dict[str, Any]]]:
    """Merge portfolio constraints + materialized prior book into config preferences."""
    from digiquant.research.dashboard_digest import portfolio_preferences_static
    from digiquant.research.graph import _atlas_config_root
    from digiquant.dashboard.profile_config import pin_profile_config_for_preflight

    try:
        prior_book = load_prior_book(client, run_date, workspace_id=config.workspace_id)
    except _SUPABASE_READ_ERRORS:
        prior_book = []

    preferences = {
        **portfolio_preferences_static(_atlas_config_root() / "portfolio.json"),
        **dict(config.preferences),
    }
    current_weights = prior_book_current_weights(prior_book)
    if current_weights:
        # Mark-to-market (#955): drift prior weights by price moves since the last run so
        # the H8 no-trade band compares against the actual current book, not stale targets.
        held = tuple(t for t in current_weights if not _is_cash_ticker(t))
        try:
            deltas = (
                query_price_deltas(client=client, tickers=held, run_date=run_date) if held else {}
            )
        except _SUPABASE_READ_ERRORS:
            deltas = {}
        preferences["current_weights"] = mark_to_market_weights(current_weights, deltas)

    # Track B (#2609): pin ProfileConfig. None → house default; overlay missing pin fails closed.
    requested_raw = config.profile_config_version_id
    requested_version = UUID(requested_raw) if requested_raw else None
    store = _profile_config_store_for_pin(client, requested_raw) if requested_raw else None
    pinned = pin_profile_config_for_preflight(
        requested_version_id=requested_version,
        store=store,
    )
    watchlist = list(pinned.watchlist) if pinned.watchlist else list(config.watchlist)
    investment_profile = (
        pinned.investment.model_dump(mode="json")
        if pinned.investment is not None
        else dict(config.investment_profile)
    )
    if pinned.themes:
        preferences = {**preferences, "profile_themes": list(pinned.themes)}
    if pinned.research_budget_usd is not None:
        preferences = {
            **preferences,
            "research_budget_usd": str(pinned.research_budget_usd),
        }

    seam = pin_seam_config(
        requested_version_id=requested_version,
        workspace_id=UUID(str(config.workspace_id)) if config.workspace_id else None,
    )
    hydrated = AtlasConfigBundle(
        watchlist=watchlist,
        investment_profile=investment_profile,
        hedge_funds=list(config.hedge_funds),
        preferences=preferences,
        macro_series=list(config.macro_series),
        profile_config_version_id=str(pinned.version_id),
        profile_config=pinned.model_dump(mode="json"),
        workspace_id=seam.workspace_id,
    )
    return hydrated, prior_book


def _resolve_research_state_attempt_id(deps: PreflightDeps) -> str:
    """Outer-retry attempt string for ResearchStatePin.attempt_id."""
    if deps.research_state_attempt_id is not None and deps.research_state_attempt_id.strip():
        return deps.research_state_attempt_id.strip()
    raw = env_lookup(ATTEMPT).strip()
    if raw:
        return raw
    return "1"


def _pin_research_state_update(deps: PreflightDeps, state: AtlasResearchState) -> dict[str, Any]:
    """WP12.3: select once and carry an exact research-state pin (or typed unavailable).

    Resume: if state already carries a pin dump, keep it (checkpoint / same attempt).
    Missing store or unusable state → ``state_unavailable`` (documents remain
    compatibility/shadow only — never invent exact state).
    """
    from uuid import UUID

    from digiquant.dashboard.research_retrieval.models import ResearchStatePin
    from digiquant.dashboard.research_retrieval.pin import (
        STATE_UNAVAILABLE,
        pin_research_state_for_preflight,
    )
    from digiquant.dashboard.research_retrieval.store import ResearchStateStore

    # Checkpoint / mid-run resume already has the authoritative pin.
    if state.research_state_pin is not None and state.research_state_status == "pinned":
        return {}

    if deps.research_state_store is None:
        return {
            "research_state_pin": None,
            "research_state_status": STATE_UNAVAILABLE,
            "research_state_unavailable_reason": (
                "research_state_store not wired; compatibility documents only (shadow)"
            ),
        }

    store = deps.research_state_store
    if not isinstance(store, ResearchStateStore):
        return {
            "research_state_pin": None,
            "research_state_status": STATE_UNAVAILABLE,
            "research_state_unavailable_reason": (
                f"research_state_store must be ResearchStateStore; got {type(store).__name__}"
            ),
        }

    try:
        cutoff = require_knowledge_cutoff_at(state)
    except ValueError as exc:
        return {
            "research_state_pin": None,
            "research_state_status": STATE_UNAVAILABLE,
            "research_state_unavailable_reason": str(exc),
        }

    explicit: UUID | None = None
    if state.requested_research_state_version_id:
        try:
            explicit = UUID(state.requested_research_state_version_id)
        except ValueError:
            return {
                "research_state_pin": None,
                "research_state_status": STATE_UNAVAILABLE,
                "research_state_unavailable_reason": (
                    f"invalid requested_research_state_version_id "
                    f"{state.requested_research_state_version_id!r}"
                ),
            }

    result = pin_research_state_for_preflight(
        store=store,
        run_id=str(state.run_id),
        attempt_id=_resolve_research_state_attempt_id(deps),
        knowledge_cutoff_at=cutoff,
        explicit_state_version_id=explicit,
        pinned_at=cutoff,
    )
    if result.status == "pinned" and result.pin is not None:
        pin: ResearchStatePin = result.pin
        return {
            "research_state_pin": pin.model_dump(mode="json"),
            "research_state_status": "pinned",
            "research_state_unavailable_reason": None,
        }
    return {
        "research_state_pin": None,
        "research_state_status": STATE_UNAVAILABLE,
        "research_state_unavailable_reason": result.unavailable_reason,
    }


def _outcome_maturation_update(deps: PreflightDeps, state: AtlasResearchState) -> dict[str, Any]:
    """WP15.6: mature prior outcomes and pin one structured lesson at cutoff."""
    from digiquant.research.phases.outcome_maturation import (
        OutcomeMaturationDeps,
        outcome_lesson_preflight_update,
        pin_outcome_lesson_for_preflight,
    )

    if state.outcome_lesson_status == "pinned" and state.outcome_lesson_pin is not None:
        return {}

    maturation_deps = deps.outcome_maturation_deps
    if maturation_deps is not None and not isinstance(maturation_deps, OutcomeMaturationDeps):
        return {
            "outcome_lesson_pin": None,
            "outcome_lesson_status": "store_unavailable",
            "outcome_lesson_unavailable_reason": (
                f"outcome_maturation_deps must be OutcomeMaturationDeps; "
                f"got {type(maturation_deps).__name__}"
            ),
        }

    try:
        cutoff = require_knowledge_cutoff_at(state)
    except ValueError:
        cutoff = state.knowledge_cutoff_at

    result = pin_outcome_lesson_for_preflight(
        maturation_deps,
        knowledge_cutoff_at=cutoff,
        consuming_run_id=str(state.run_id) if state.run_id is not None else None,
        resume_pin=state.outcome_lesson_pin,
        resume_status=state.outcome_lesson_status,
    )
    return outcome_lesson_preflight_update(result)


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
            prior_deliberation = load_prior_deliberation_summaries(
                deps.client, state.run_date, held_tickers
            )
        except _SUPABASE_READ_ERRORS:
            prior_deliberation = {}
        try:
            active_theses = load_active_theses_rows(deps.client, state.run_date)
        except _SUPABASE_READ_ERRORS:
            active_theses = []
        try:
            portfolio_performance = load_portfolio_performance_snapshot(
                deps.client, state.run_date, workspace_id=config.workspace_id
            )
        except _SUPABASE_READ_ERRORS:
            portfolio_performance = {}

        prior_context = PriorContext(
            last_snapshots=prior_context.last_snapshots,
            latest_segments=prior_context.latest_segments,
            active_theses=active_theses,
            decision_lessons=lessons,
            prior_book=prior_book,
            prior_analyst_by_ticker=prior_analyst,
            prior_deliberation_by_ticker=prior_deliberation,
            portfolio_performance=portfolio_performance,
        )

        update: dict[str, Any] = {
            "config": config,
            "prior_context": prior_context,
            "data_layer": data_layer,
        }
        update.update(_pin_research_state_update(deps, state))
        update.update(_outcome_maturation_update(deps, state))

        from digiquant.dashboard.research_retrieval.h7_prerequisites import (
            build_h7_prerequisite_snapshot,
        )

        prior_effective_ids = tuple(
            sorted(
                {
                    str(row.get("effective_forecast_id"))
                    for row in prior_deliberation.values()
                    if isinstance(row, dict) and row.get("effective_forecast_id")
                }
            )
        )
        try:
            cutoff = state.knowledge_cutoff_at
        except Exception:
            cutoff = None
        pin_raw = update.get("research_state_pin")
        if not isinstance(pin_raw, dict) and isinstance(state.research_state_pin, dict):
            pin_raw = state.research_state_pin
        lesson_pin_raw = update.get("outcome_lesson_pin")
        if not isinstance(lesson_pin_raw, dict) and isinstance(state.outcome_lesson_pin, dict):
            lesson_pin_raw = state.outcome_lesson_pin
        snapshot = build_h7_prerequisite_snapshot(
            client=deps.client,
            run_date=state.run_date,
            knowledge_cutoff_at=cutoff,
            research_state_pin=pin_raw if isinstance(pin_raw, dict) else None,
            prior_effective_forecast_ids=prior_effective_ids,
            outcome_lesson_pin=lesson_pin_raw if isinstance(lesson_pin_raw, dict) else None,
        )
        if snapshot is not None:
            update["h7_prerequisite_snapshot"] = snapshot.model_dump(mode="json")

        return update

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
        if skip_overlay_shared_register(state.config.workspace_id):
            logger.info(
                "overlay skip shared register decision_log / forecast outcomes "
                "(house-only leftover uniques)"
            )
            return {}
        resolve_pending(
            client=deps.client,
            run_date=state.run_date,
            reflector=deps.reflector,
            workspace_id=state.config.workspace_id,
        )
        # WP5.2 — typed forecast outcomes beside decision_log reflection.
        try:
            cutoff = require_knowledge_cutoff_at(state)
        except ValueError:
            logger.info("forecast outcomes: skip resolve — knowledge_cutoff_at missing on state")
        else:
            resolve_matured_forecast_outcomes(
                client=deps.client,
                run_date=state.run_date,
                knowledge_cutoff_at=cutoff,
                current_run_id=str(state.run_id) if state.run_id is not None else None,
            )
            resolve_realized_action_cost_outcomes_from_state(
                client=deps.client,
                state=state,
            )
        return {}

    return reflect
