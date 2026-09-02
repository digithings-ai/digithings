"""WP13.4 — plan portfolio research attention after H4 without changing roster (#2930).

Invokes :func:`plan_research_attention` at H4 end over the fixed focus roster and
branches in H5/H6 provider paths. ``off`` / ``shadow`` / ``enforce`` via
``OLYMPUS_RESEARCH_ATTENTION_MODE``. Not a graph node; cannot mutate H4 roster.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
    Mapping,
)
from uuid import UUID

from digiquant.research.research_attention import (
    OLYMPUS_RESEARCH_ATTENTION_MODE_ENV,
    attention_store_for_run,
    lookup_attention_decision,
    resolve_research_attention_rollout_mode,
)
from digiquant.research.state import FocusRosterEntry
from digiquant.research.supabase_io import prior_book_current_weights
from digiquant.dashboard.edit_mode.models import PriorPublished
from digiquant.dashboard.edit_mode.prior import artifact_document_key
from digiquant.portfolio.candidates import holdings_from_prior_book
from digiquant.portfolio.state import PortfolioState
from digiquant.dashboard.research_retrieval.planner import (
    AttentionDecision,
    AttentionFeatures,
    AttentionMode,
    AttentionPlan,
    AttentionRolloutMode,
    AttentionTargetKind,
    build_h6_decision_features,
    load_research_attention_policy,
    plan_research_attention,
    route_attention,
)

logger = logging.getLogger(__name__)

H5EnforcePath = Literal["carry", "metric_patch", "full"] | None
H6EnforcePath = Literal["challenge", "carry"] | None

_EXPLORATORY_REASONS = frozenset({"technical", "momentum", "other"})


def _analyst_artifact_key(ticker: str) -> tuple[str, str]:
    return ("analyst", ticker.strip().upper())


def _load_prior_analyst_published(state: PortfolioState, ticker: str) -> PriorPublished | None:
    artifact_key = _analyst_artifact_key(ticker)
    doc_key = artifact_document_key(artifact_key)
    row = state.prior_context.latest_segments.get(doc_key)
    if isinstance(row, dict):
        payload = row.get("payload")
        if isinstance(payload, dict):
            raw_date = row.get("date")
            try:
                prior_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                prior_date = state.run_date
            return PriorPublished(date=prior_date, document_key=doc_key, payload=payload)
    slim = state.prior_context.prior_analyst_by_ticker.get(ticker.strip().upper(), {})
    if not isinstance(slim, dict) or not slim:
        slim = state.prior_context.prior_analyst_by_ticker.get(ticker, {})
    if not isinstance(slim, dict) or not slim:
        return None
    return PriorPublished(
        date=date.fromisoformat(str(slim.get("date", state.run_date))[:10]),
        document_key=doc_key,
        payload={"body": dict(slim)},
    )


def ticker_target_key(ticker: str) -> str:
    """Canonical portfolio ticker attention target (``ticker:SPY``)."""
    return f"ticker:{ticker.strip().upper()}"


def _state_version_id(state: PortfolioState) -> UUID | None:
    pin = state.research_state_pin
    if not isinstance(pin, dict):
        return None
    raw = pin.get("state_version_id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def _roster_entry_for(state: PortfolioState, ticker: str) -> FocusRosterEntry | None:
    sym = ticker.strip().upper()
    for entry in state.phase_portfolio.focus_roster:
        if entry.ticker.upper() == sym:
            return entry
    return None


def _staleness_days(prior: PriorPublished | None, run_date: date) -> int | None:
    if prior is None:
        return None
    content_date = prior.content_date or prior.date
    return max(0, (run_date - content_date).days)


def _prior_analyst_body(state: PortfolioState, ticker: str) -> dict[str, Any] | None:
    sym = ticker.strip().upper()
    prior = state.prior_context.prior_analyst_by_ticker.get(sym)
    if not isinstance(prior, dict):
        prior = state.prior_context.prior_analyst_by_ticker.get(ticker)
    return prior if isinstance(prior, dict) else None


def build_ticker_attention_features(
    state: PortfolioState,
    ticker: str,
    *,
    analyst: Mapping[str, Any] | None = None,
) -> AttentionFeatures:
    """Structured features for one portfolio ticker (H4 pre-provider or post-H5)."""
    entry = _roster_entry_for(state, ticker)
    roster_reason = entry.roster_reason if entry is not None else "other"
    held_set = set(holdings_from_prior_book(state.prior_context.prior_book))
    sym = ticker.strip().upper()
    held = sym in held_set
    weights = prior_book_current_weights(list(state.prior_context.prior_book))
    weight_pct = float(weights.get(sym, 0.0) or 0.0)
    prior_analyst = _prior_analyst_body(state, ticker)
    analyst_blob: dict[str, Any] = dict(analyst) if isinstance(analyst, Mapping) else {}
    if not analyst_blob and prior_analyst is not None:
        analyst_blob = prior_analyst
    price_delta = state.price_deltas.get(sym)
    if price_delta is None:
        price_delta = state.price_deltas.get(ticker)
    prior_pub = _load_prior_analyst_published(state, ticker)
    pin_raw = _state_version_id(state)
    exploration_slot = roster_reason in _EXPLORATORY_REASONS
    h6 = build_h6_decision_features(
        ticker=sym,
        roster_reason=roster_reason,
        held=held,
        weight_pct=weight_pct,
        analyst=analyst_blob,
        prior_analyst=prior_analyst,
        price_delta=float(price_delta) if price_delta is not None else None,
    )
    return AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key=sym,
        state_version_id=str(pin_raw) if pin_raw is not None else None,
        h6=h6,
        has_prior=prior_pub is not None,
        force_full_rewrite=state.refresh_scope in ("all", "portfolio"),
        has_structured_delta=price_delta is not None,
        staleness_days=_staleness_days(prior_pub, state.run_date),
        exploration_slot=exploration_slot,
    )


def collect_portfolio_attention_features(state: PortfolioState) -> tuple[AttentionFeatures, ...]:
    """All ticker targets from the fixed H4 focus roster."""
    if state.custom_prompt:
        return ()
    return tuple(
        build_ticker_attention_features(state, entry.ticker)
        for entry in state.phase_portfolio.focus_roster
    )


def plan_portfolio_research_attention(state: PortfolioState) -> AttentionPlan | None:
    """Build the post-H4 research attention plan; ``None`` when mode is off."""
    rollout = resolve_research_attention_rollout_mode()
    if rollout is AttentionRolloutMode.OFF:
        return None
    features = collect_portfolio_attention_features(state)
    if not features:
        return None
    return plan_research_attention(
        run_id=str(state.run_id),
        state_version_id=_state_version_id(state),
        features=features,
        rollout_mode=rollout,
    )


def persist_portfolio_research_attention_plan(
    *,
    state: PortfolioState,
    plan: AttentionPlan,
    attempt_id: str | None = None,
    recorded_at: datetime | None = None,
) -> None:
    """Append portfolio plan + decisions to the run-scoped :class:`AttentionStore`."""
    stamp = recorded_at or datetime.now(tz=UTC)
    resolved_attempt = attempt_id or f"portfolio-h4:{state.run_id}"
    store = attention_store_for_run(str(state.run_id))
    store.append_plan(plan, attempt_id=resolved_attempt, recorded_at=stamp)


def plan_and_persist_portfolio_research_attention(state: PortfolioState) -> AttentionPlan | None:
    """Plan after H4 roster is fixed and persist reasons."""
    plan = plan_portfolio_research_attention(state)
    if plan is not None:
        persist_portfolio_research_attention_plan(state=state, plan=plan)
    return plan


def _load_portfolio_attention_plan(state: PortfolioState) -> AttentionPlan | None:
    raw = state.portfolio_research_attention_plan
    if raw is None:
        return None
    if isinstance(raw, AttentionPlan):
        return raw
    return AttentionPlan.model_validate(raw)


def resolve_portfolio_research_attention_plan(state: PortfolioState) -> AttentionPlan | None:
    """Return the portfolio plan for provider gating."""
    rollout = resolve_research_attention_rollout_mode()
    if rollout is AttentionRolloutMode.OFF or state.custom_prompt:
        return None
    plan = _load_portfolio_attention_plan(state)
    if plan is not None:
        return plan
    if state.phase_portfolio.focus_roster:
        return plan_portfolio_research_attention(state)
    if rollout is AttentionRolloutMode.ENFORCE:
        raise RuntimeError(
            "portfolio research attention plan missing before provider work "
            f"(run_id={state.run_id}); H4 must plan first"
        )
    return None


def h4_phase_attention_update(state: PortfolioState) -> dict[str, Any]:
    """State update dict after H4 roster is fixed — plan before H5/H6 providers."""
    plan = plan_and_persist_portfolio_research_attention(state)
    if plan is None:
        return {}
    return {"portfolio_research_attention_plan": plan.model_dump(mode="json")}


def _h5_enforce_path_for_mode(mode: AttentionMode) -> H5EnforcePath:
    if mode is AttentionMode.CARRY:
        return "carry"
    if mode is AttentionMode.METRIC_PATCH:
        return "metric_patch"
    if mode is AttentionMode.DEEP_REFRESH:
        return "full"
    return None


def research_attention_h5_enforce_path(
    state: PortfolioState,
    *,
    ticker: str,
) -> H5EnforcePath:
    """Return early H5 path under enforce mode; ``None`` for off/shadow/incumbent."""
    if resolve_research_attention_rollout_mode() is not AttentionRolloutMode.ENFORCE:
        return None
    plan = resolve_portfolio_research_attention_plan(state)
    if plan is None:
        return None
    decision = lookup_attention_decision(plan, ticker.strip().upper())
    if decision is None:
        return None
    return _h5_enforce_path_for_mode(decision.mode)


def resolve_h6_attention_decision(
    state: PortfolioState,
    ticker: str,
    analyst: Mapping[str, Any],
) -> AttentionDecision | None:
    """Re-route one ticker after H5 features (conditional H6)."""
    rollout = resolve_research_attention_rollout_mode()
    if rollout is AttentionRolloutMode.OFF or state.custom_prompt:
        return None
    features = build_ticker_attention_features(state, ticker, analyst=analyst)
    policy = load_research_attention_policy()
    actuated = rollout is AttentionRolloutMode.ENFORCE
    return route_attention(features, policy, actuated=actuated)


def research_attention_h6_enforce_path(
    state: PortfolioState,
    ticker: str,
    analyst: Mapping[str, Any],
) -> H6EnforcePath:
    """Return H6 path under enforce after H5 features; ``None`` for off/shadow."""
    if resolve_research_attention_rollout_mode() is not AttentionRolloutMode.ENFORCE:
        return None
    decision = resolve_h6_attention_decision(state, ticker, analyst)
    if decision is None:
        return None
    if decision.mode is AttentionMode.CHALLENGE:
        return "challenge"
    return "carry"


def apply_analyst_metric_patch(
    state: PortfolioState,
    ticker: str,
    prior: PriorPublished,
    *,
    roster_entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Deterministic H5 structured update — zero provider calls (#2930)."""
    body = dict(prior.payload)
    inner = body.get("body") if isinstance(body.get("body"), dict) else body
    if not isinstance(inner, dict):
        inner = {}
    sym = ticker.strip().upper()
    if sym in state.price_deltas:
        inner["structured_price_delta"] = state.price_deltas[sym]
    inner["metric_patch"] = True
    inner["ticker"] = sym
    inner["roster_reason"] = roster_entry.get("roster_reason")
    if isinstance(body.get("body"), dict):
        body["body"] = inner
    else:
        body = inner
    body["date"] = state.run_date.isoformat()
    return body


__all__ = [
    "H5EnforcePath",
    "H6EnforcePath",
    "OLYMPUS_RESEARCH_ATTENTION_MODE_ENV",
    "apply_analyst_metric_patch",
    "build_ticker_attention_features",
    "collect_portfolio_attention_features",
    "h4_phase_attention_update",
    "lookup_attention_decision",
    "persist_portfolio_research_attention_plan",
    "plan_and_persist_portfolio_research_attention",
    "plan_portfolio_research_attention",
    "research_attention_h5_enforce_path",
    "research_attention_h6_enforce_path",
    "resolve_h6_attention_decision",
    "resolve_portfolio_research_attention_plan",
    "ticker_target_key",
]
