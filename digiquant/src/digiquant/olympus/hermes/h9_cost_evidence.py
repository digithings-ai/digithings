"""Build prospective cost/liquidity bundles after authoritative order intents exist (#2709).

Runs at the H9 boundary once ``append_commit_chain`` has minted ``order_intent_id``
rows. Observational only — never feeds turnover or sizing.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

import polars as pl

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.action_cost_inputs import (
    ActionCostBindingError,
    action_cost_input_from_order,
)
from digiquant.olympus.hermes.cost_liquidity import (
    DEFAULT_ADV_LOOKBACK_DAYS,
    CostLiquidityBundle,
    adv_from_price_history,
    cost_coefficients_from_policy,
    estimate_action_cost,
    prospective_observations_from_row,
)
from digiquant.olympus.hermes.models.portfolio_ledger import (
    DecisionIntent,
    OrderIntent,
    PortfolioCommit,
)
from digiquant.olympus.hermes.models.risk_policy import RiskPolicy
from digiquant.olympus.temporal import require_utc_datetime

logger = logging.getLogger(__name__)

DECISION_INTENTS = "portfolio_ledger_decision_intents"
REQUESTED_TARGETS = "portfolio_ledger_requested_targets"
APPROVED_TARGETS = "portfolio_ledger_approved_targets"
ORDER_INTENTS = "portfolio_ledger_order_intents"
_PRICE_HISTORY = "price_history"
_PRICE_TECHNICALS = "price_technicals"


def investor_currency_from_state(state: AtlasResearchState) -> str | None:
    """Resolve explicit portfolio currency — never infer USD or NAV."""
    prefs = getattr(getattr(state, "config", None), "preferences", None) or {}
    raw = prefs.get("investor_currency") or prefs.get("currency")
    if raw is None:
        return None
    code = str(raw).strip().upper()
    return code if len(code) >= 3 else None


def _fetch_technicals_row(
    *,
    client: SupabaseClient,
    symbol: str,
    session_date: str,
) -> dict[str, Any] | None:
    resp = (
        client.table(_PRICE_TECHNICALS)
        .select("date, hist_vol_21, atr_pct")
        .eq("ticker", symbol.strip().upper())
        .eq("date", session_date)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _merge_price_and_technicals(
    price_row: dict[str, Any] | None,
    tech_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if price_row is None and tech_row is None:
        return None
    merged: dict[str, Any] = dict(price_row or {})
    if tech_row:
        for key in ("hist_vol_21", "atr_pct"):
            if merged.get(key) is None and tech_row.get(key) is not None:
                merged[key] = tech_row[key]
    return merged


def _load_technicals_history(
    *,
    client: SupabaseClient,
    symbol: str,
    as_of_session: str,
) -> pl.DataFrame:
    resp = (
        client.table(_PRICE_TECHNICALS)
        .select("date, hist_vol_21, atr_pct")
        .eq("ticker", symbol.strip().upper())
        .lte("date", as_of_session)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def _load_symbol_history(
    *,
    client: SupabaseClient,
    symbol: str,
    as_of_session: str,
    lookback_days: int,
) -> pl.DataFrame:
    resp = (
        client.table(_PRICE_HISTORY)
        .select("date, ticker, close, high, low, volume")
        .eq("ticker", symbol.strip().upper())
        .lte("date", as_of_session)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return pl.DataFrame()
    frame = pl.DataFrame(rows)
    techs = _load_technicals_history(
        client=client,
        symbol=symbol,
        as_of_session=as_of_session,
    )
    if not techs.is_empty() and "date" in techs.columns and "date" in frame.columns:
        left = frame.with_columns(pl.col("date").cast(pl.Utf8).alias("_join_date"))
        right = techs.with_columns(pl.col("date").cast(pl.Utf8).alias("_join_date"))
        tech_cols = ["_join_date"] + [c for c in ("hist_vol_21", "atr_pct") if c in right.columns]
        frame = left.join(right.select(tech_cols), on="_join_date", how="left").drop("_join_date")
    else:
        for col in ("hist_vol_21", "atr_pct"):
            if col not in frame.columns:
                frame = frame.with_columns(pl.lit(None).alias(col))
    if "date" in frame.columns:
        frame = frame.sort("date", descending=True).head(lookback_days + 5)
    return frame


def _fetch_price_row(
    *,
    client: SupabaseClient,
    symbol: str,
    session_date: str,
) -> dict[str, Any] | None:
    resp = (
        client.table(_PRICE_HISTORY)
        .select("date, close, high, low, volume")
        .eq("ticker", symbol.strip().upper())
        .eq("date", session_date)
        .limit(1)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    price_row = rows[0] if rows else None
    return _merge_price_and_technicals(
        price_row,
        _fetch_technicals_row(client=client, symbol=symbol, session_date=session_date),
    )


def _load_commit_orders(
    *,
    client: SupabaseClient,
    commit_id: UUID,
    run_date: str,
) -> list[tuple[DecisionIntent, OrderIntent, Decimal | None]]:
    """Return tradeable (decision, order, mark_price) tuples for one commit."""
    resp = (
        client.table(DECISION_INTENTS)
        .select("*")
        .eq("portfolio_commit_id", str(commit_id))
        .execute()
    )
    decisions = {
        str(row.get("symbol", "")).strip().upper(): DecisionIntent.model_validate(row)
        for row in (resp.data or [])
    }
    if not decisions:
        return []

    approved_resp = client.table(APPROVED_TARGETS).select("*").eq("run_date", run_date).execute()
    requested_resp = client.table(REQUESTED_TARGETS).select("*").eq("run_date", run_date).execute()
    order_resp = client.table(ORDER_INTENTS).select("*").eq("run_date", run_date).execute()

    decision_by_requested: dict[str, DecisionIntent] = {}
    for req in requested_resp.data or []:
        did = str(req.get("decision_intent_id") or "")
        sym = str(req.get("symbol") or "").strip().upper()
        if did and sym in decisions:
            decision_by_requested[str(req["id"])] = decisions[sym]

    approved_for_commit: dict[str, dict[str, Any]] = {}
    for appr in approved_resp.data or []:
        req_id = str(appr.get("requested_target_id") or "")
        if req_id in decision_by_requested:
            approved_for_commit[str(appr["id"])] = appr

    out: list[tuple[DecisionIntent, OrderIntent, Decimal | None]] = []
    for order_row in order_resp.data or []:
        appr_id = str(order_row.get("approved_target_id") or "")
        if appr_id not in approved_for_commit:
            continue
        order = OrderIntent.model_validate(order_row)
        sym = order.symbol.strip().upper()
        decision = decisions.get(sym)
        if decision is None:
            continue
        mark: Decimal | None = None
        price_row = _fetch_price_row(
            client=client,
            symbol=sym,
            session_date=run_date,
        )
        if price_row and price_row.get("close") is not None:
            try:
                mark = Decimal(str(price_row["close"]))
            except (ArithmeticError, ValueError):
                mark = None
        out.append((decision, order, mark))
    return out


def build_cost_bundles_for_commit(
    *,
    client: SupabaseClient,
    state: AtlasResearchState,
    commit_id: UUID,
    policy: RiskPolicy,
) -> list[CostLiquidityBundle]:
    """Estimate observational costs for every order intent in one ledger commit."""
    run_date = state.run_date.isoformat()
    currency = investor_currency_from_state(state)
    if currency is None:
        logger.warning("h9 cost evidence: currency_missing — skipping estimates (no false USD)")
        return []
    cutoff = state.knowledge_cutoff_at
    resolved_at = (
        require_utc_datetime(cutoff, field_name="knowledge_cutoff_at")
        if cutoff is not None
        else datetime.combine(state.run_date, datetime.min.time(), tzinfo=UTC)
    )

    commit_resp = (
        client.table("portfolio_ledger_commits")
        .select("*")
        .eq("id", str(commit_id))
        .limit(1)
        .execute()
    )
    commit_rows = list(commit_resp.data or [])
    if not commit_rows:
        logger.warning("h9 cost evidence: commit %s not found on disk", commit_id)
        return []
    commit = PortfolioCommit.model_validate(commit_rows[0])

    bundles: list[CostLiquidityBundle] = []
    for decision, order, mark in _load_commit_orders(
        client=client,
        commit_id=commit_id,
        run_date=run_date,
    ):
        try:
            action = action_cost_input_from_order(
                commit=commit,
                decision=decision,
                order=order,
                currency=currency,
                mark_price=mark,
            )
        except ActionCostBindingError as exc:
            logger.info(
                "h9 cost evidence: skip order %s (%s)",
                order.id,
                exc,
            )
            continue

        price_row = _fetch_price_row(
            client=client,
            symbol=action.symbol,
            session_date=run_date,
        )
        coeffs = cost_coefficients_from_policy(policy)
        history = _load_symbol_history(
            client=client,
            symbol=action.symbol,
            as_of_session=run_date,
            lookback_days=coeffs.adv_lookback_days or DEFAULT_ADV_LOOKBACK_DAYS,
        )
        adv_shares, adv_dollars = adv_from_price_history(
            history,
            symbol=action.symbol,
            as_of_session=state.run_date,
            lookback_days=coeffs.adv_lookback_days,
        )
        observations = prospective_observations_from_row(
            session_date=state.run_date,
            symbol=action.symbol,
            row=price_row or {},
            observed_at=resolved_at,
            known_at=resolved_at,
            adv_shares=adv_shares,
            adv_dollars=adv_dollars,
        )
        try:
            bundle = estimate_action_cost(
                action,
                observations,
                policy,
                estimated_at=resolved_at,
            )
        except Exception as exc:
            logger.warning(
                "h9 cost evidence: estimate failed for order %s (%s: %s)",
                order.id,
                type(exc).__name__,
                exc,
            )
            continue
        bundles.append(bundle)
    return bundles


__all__ = [
    "build_cost_bundles_for_commit",
    "investor_currency_from_state",
]
