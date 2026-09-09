"""Pure Decimal/Polars event-boundary period accounting engine (#2596).

No I/O, no pandas, no broker paths. Callers assemble opening holdings/cash, fills/costs,
and closing marks; this module returns an ``AccountingPeriod`` that is either reconciled
within the versioned tolerance or explicitly non-final (estimated / incomplete / failed).

Polars is used to order and group tabular fill/holding rows; every money path is Decimal.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

import polars as pl

from digiquant.dashboard.accounting.models import (
    AccountingPeriod,
    AccountingPolicy,
    ClosingHolding,
    CorporateActionKind,
    DividendPolicy,
    FillSide,
    MarkObservation,
    PeriodAccountingInput,
    PeriodFill,
    PeriodStatus,
    QualityReason,
    SplitPolicy,
    TickerPeriodResult,
)

# Stable namespace for deterministic period ids (exact same-date retry → same id).
_PERIOD_ID_NAMESPACE = UUID("a3c91e7b-4d2f-5e8a-9b1c-6d0e7f8a9b2c")

_ZERO = Decimal("0")


def period_id_for_input(inp: PeriodAccountingInput) -> UUID:
    """Deterministic id so an exact same-input retry reproduces the same period row."""
    digest = hashlib.sha256(_canonical_input_bytes(inp)).hexdigest()
    return uuid5(
        _PERIOD_ID_NAMESPACE,
        f"{inp.period_date.isoformat()}|{inp.policy.policy_version_id}|{digest}",
    )


def compute_period(inp: PeriodAccountingInput) -> AccountingPeriod:
    """Compute one event-boundary accounting period from authoritative inputs."""
    reasons: list[QualityReason] = []
    policy = inp.policy

    opening_qty = {h.symbol: h.quantity for h in inp.opening_holdings}
    opening_marks = _marks_by_symbol(inp.opening_marks)
    closing_marks = _marks_by_symbol(inp.closing_marks)

    if inp.benchmark is not None and inp.benchmark.period_date != inp.period_date:
        reasons.append(QualityReason.BENCHMARK_BOUNDARY_MISMATCH)

    qty = dict(opening_qty)
    cash = inp.opening_cash
    cash_pnl = _ZERO
    fees_by_symbol: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    slippage_by_symbol: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    buy_notional: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    sell_notional: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    ticker_reasons: dict[str, list[QualityReason]] = defaultdict(list)

    # Corporate actions first (effective on period_date), then fills in time order.
    for action in sorted(inp.corporate_actions, key=lambda a: (a.effective_date, a.symbol)):
        if action.effective_date != inp.period_date:
            continue
        if action.kind is CorporateActionKind.DIVIDEND_CASH:
            if policy.dividend_policy is DividendPolicy.IGNORE:
                reasons.append(QualityReason.CORPORATE_ACTION_IGNORED)
                continue
            held = qty.get(action.symbol, _ZERO)
            dividend_cash = held * action.amount
            cash += dividend_cash
            cash_pnl += dividend_cash
        elif action.kind is CorporateActionKind.SPLIT:
            if policy.split_policy is SplitPolicy.IGNORE:
                reasons.append(QualityReason.CORPORATE_ACTION_IGNORED)
                continue
            held = qty.get(action.symbol, _ZERO)
            qty[action.symbol] = held * action.amount

    fills_frame = _fills_frame(inp.fills)
    ordered_fills = (
        list(inp.fills)
        if fills_frame.is_empty()
        else [
            inp.fills[i]
            for i in fills_frame.sort(["executed_at", "symbol"]).get_column("_idx").to_list()
        ]
    )

    for fill in ordered_fills:
        sym = fill.symbol
        if fill.side is FillSide.BUY:
            if opening_qty.get(sym, _ZERO) == _ZERO and qty.get(sym, _ZERO) == _ZERO:
                # Informational on the ticker only — an open-gap buy is a valid final period.
                ticker_reasons[sym].append(QualityReason.OPEN_GAP)
            qty[sym] = qty.get(sym, _ZERO) + fill.quantity
            notional = fill.quantity * fill.price
            buy_notional[sym] += notional
            cash -= notional + fill.fee + fill.slippage
        else:
            qty[sym] = qty.get(sym, _ZERO) - fill.quantity
            notional = fill.quantity * fill.price
            sell_notional[sym] += notional
            cash += notional - fill.fee - fill.slippage
        fees_by_symbol[sym] += fill.fee
        slippage_by_symbol[sym] += fill.slippage
        if qty.get(sym, _ZERO) < _ZERO:
            reasons.append(QualityReason.NEGATIVE_QUANTITY)
            ticker_reasons[sym].append(QualityReason.NEGATIVE_QUANTITY)

    # Drop exact-zero residual lots from the closing book view.
    qty = {s: q for s, q in qty.items() if q != _ZERO}

    symbols = sorted(
        set(opening_qty)
        | set(qty)
        | set(opening_marks)
        | set(closing_marks)
        | set(buy_notional)
        | set(sell_notional)
        | {f.symbol for f in inp.fills}
        | {a.symbol for a in inp.corporate_actions}
    )

    period_end = datetime(
        inp.period_date.year, inp.period_date.month, inp.period_date.day, 23, 59, 59, tzinfo=UTC
    )

    ticker_results: list[TickerPeriodResult] = []
    closing_holdings: list[ClosingHolding] = []
    gross_total = _ZERO
    net_total = _ZERO
    fees_total = _ZERO
    slippage_total = _ZERO
    closing_mv = _ZERO
    opening_mv = _ZERO

    for sym in symbols:
        q0 = opening_qty.get(sym, _ZERO)
        q1 = qty.get(sym, _ZERO)
        m0 = opening_marks.get(sym)
        m1 = closing_marks.get(sym)
        local_reasons = list(dict.fromkeys(ticker_reasons.get(sym, [])))

        if q0 > _ZERO and m0 is None:
            reasons.append(QualityReason.MISSING_OPENING_MARK)
            local_reasons.append(QualityReason.MISSING_OPENING_MARK)
        if q1 > _ZERO and m1 is None:
            reasons.append(QualityReason.MISSING_CLOSING_MARK)
            local_reasons.append(QualityReason.MISSING_CLOSING_MARK)
        if m1 is not None and _is_stale(m1, period_end, policy.max_mark_age):
            reasons.append(QualityReason.STALE_CLOSING_MARK)
            local_reasons.append(QualityReason.STALE_CLOSING_MARK)

        p0 = m0.price if m0 is not None else None
        p1 = m1.price if m1 is not None else None
        if q0 > _ZERO and p0 is not None:
            opening_mv += q0 * p0

        # gross = ΔMV + sell proceeds − buy spend (price path only; costs separate)
        mv0 = (q0 * p0) if p0 is not None else _ZERO
        mv1 = (q1 * p1) if (q1 > _ZERO and p1 is not None) else _ZERO
        if q1 > _ZERO and p1 is None:
            mv1 = _ZERO
        gross = mv1 - mv0 + sell_notional[sym] - buy_notional[sym]
        fees = fees_by_symbol[sym]
        slip = slippage_by_symbol[sym]
        net = gross - fees - slip

        gross_total += gross
        net_total += net
        fees_total += fees
        slippage_total += slip
        if q1 > _ZERO and p1 is not None:
            closing_mv += q1 * p1
            closing_holdings.append(
                ClosingHolding(symbol=sym, quantity=q1, mark=p1, market_value=q1 * p1)
            )
        elif q1 > _ZERO:
            closing_holdings.append(
                ClosingHolding(symbol=sym, quantity=q1, mark=None, market_value=None)
            )

        ticker_results.append(
            TickerPeriodResult(
                symbol=sym,
                opening_quantity=q0,
                closing_quantity=q1,
                opening_mark=p0,
                closing_mark=p1,
                gross_pnl=gross,
                fees=fees,
                slippage=slip,
                net_pnl=net,
                contribution=None,  # filled after E0 known
                quality_reasons=tuple(dict.fromkeys(local_reasons)),
            )
        )

    opening_equity = inp.opening_cash + opening_mv
    closing_equity = cash + closing_mv
    residual = closing_equity - (opening_equity + net_total + cash_pnl)

    if opening_equity == _ZERO:
        reasons.append(QualityReason.ZERO_OPENING_EQUITY)

    tol = _effective_tolerance(opening_equity, policy)
    if abs(residual) > tol:
        reasons.append(QualityReason.RESIDUAL_EXCEEDED)

    # Deduplicate reasons while preserving order.
    reasons = list(dict.fromkeys(reasons))
    status = _resolve_status(reasons, residual, tol)

    contributions: list[TickerPeriodResult] = []
    cash_contribution: Decimal | None
    if opening_equity > _ZERO:
        cash_contribution = cash_pnl / opening_equity
        for row in ticker_results:
            contributions.append(
                row.model_copy(update={"contribution": row.net_pnl / opening_equity})
            )
    else:
        cash_contribution = None
        contributions = list(ticker_results)

    benchmark_return: Decimal | None = None
    benchmark_symbol = None
    if inp.benchmark is not None:
        benchmark_symbol = inp.benchmark.symbol
        benchmark_return = (
            inp.benchmark.closing_price - inp.benchmark.opening_price
        ) / inp.benchmark.opening_price

    return AccountingPeriod(
        id=period_id_for_input(inp),
        period_date=inp.period_date,
        policy_version_id=policy.policy_version_id,
        status=status,
        quality_reasons=tuple(reasons),
        opening_equity=opening_equity,
        closing_equity=closing_equity,
        opening_cash=inp.opening_cash,
        closing_cash=cash,
        cash_pnl=cash_pnl,
        cash_contribution=cash_contribution,
        gross_pnl_total=gross_total,
        net_pnl_total=net_total,
        fees_total=fees_total,
        slippage_total=slippage_total,
        residual=residual,
        absolute_tolerance=policy.absolute_tolerance,
        relative_tolerance=policy.relative_tolerance,
        benchmark_symbol=benchmark_symbol,
        benchmark_return=benchmark_return,
        ticker_results=tuple(contributions),
        closing_holdings=tuple(sorted(closing_holdings, key=lambda h: h.symbol)),
    )


def _marks_by_symbol(marks: tuple[MarkObservation, ...]) -> dict[str, MarkObservation]:
    return {m.symbol: m for m in marks}


def _fills_frame(fills: tuple[PeriodFill, ...]) -> pl.DataFrame:
    if not fills:
        return pl.DataFrame(
            schema={
                "_idx": pl.Int64,
                "symbol": pl.Utf8,
                "executed_at": pl.Datetime(time_zone="UTC"),
            }
        )
    return pl.DataFrame(
        {
            "_idx": list(range(len(fills))),
            "symbol": [f.symbol for f in fills],
            "executed_at": [f.executed_at for f in fills],
        }
    )


def _is_stale(mark: MarkObservation, period_end: datetime, max_age: timedelta) -> bool:
    return period_end - mark.observed_at > max_age


def _effective_tolerance(opening_equity: Decimal, policy: AccountingPolicy) -> Decimal:
    rel = abs(opening_equity) * policy.relative_tolerance
    return max(policy.absolute_tolerance, rel)


def _resolve_status(reasons: list[QualityReason], residual: Decimal, tol: Decimal) -> PeriodStatus:
    hard = {
        QualityReason.RESIDUAL_EXCEEDED,
        QualityReason.NEGATIVE_QUANTITY,
        QualityReason.BENCHMARK_BOUNDARY_MISMATCH,
    }
    if any(r in hard for r in reasons) or abs(residual) > tol:
        return PeriodStatus.FAILED
    incomplete = {
        QualityReason.MISSING_OPENING_MARK,
        QualityReason.MISSING_CLOSING_MARK,
        QualityReason.ZERO_OPENING_EQUITY,
    }
    if any(r in incomplete for r in reasons):
        return PeriodStatus.INCOMPLETE
    estimated = {
        QualityReason.STALE_CLOSING_MARK,
        QualityReason.CORPORATE_ACTION_IGNORED,
    }
    if any(r in estimated for r in reasons):
        return PeriodStatus.ESTIMATED
    return PeriodStatus.FINAL


def _canonical_input_bytes(inp: PeriodAccountingInput) -> bytes:
    """Stable JSON digest for exact-retry identity (not a security hash)."""

    def dec(value: Decimal) -> str:
        return format(value, "f")

    payload = {
        "period_date": inp.period_date.isoformat(),
        "policy": {
            "policy_version_id": inp.policy.policy_version_id,
            "absolute_tolerance": dec(inp.policy.absolute_tolerance),
            "relative_tolerance": dec(inp.policy.relative_tolerance),
            "max_mark_age_seconds": int(inp.policy.max_mark_age.total_seconds()),
            "dividend_policy": inp.policy.dividend_policy.value,
            "split_policy": inp.policy.split_policy.value,
        },
        "opening_cash": dec(inp.opening_cash),
        "opening_holdings": [
            {"symbol": h.symbol, "quantity": dec(h.quantity)}
            for h in sorted(inp.opening_holdings, key=lambda x: x.symbol)
        ],
        "opening_marks": [
            {
                "symbol": m.symbol,
                "price": dec(m.price),
                "as_of": m.as_of.isoformat(),
                "observed_at": m.observed_at.isoformat(),
            }
            for m in sorted(inp.opening_marks, key=lambda x: x.symbol)
        ],
        "closing_marks": [
            {
                "symbol": m.symbol,
                "price": dec(m.price),
                "as_of": m.as_of.isoformat(),
                "observed_at": m.observed_at.isoformat(),
            }
            for m in sorted(inp.closing_marks, key=lambda x: x.symbol)
        ],
        "fills": [
            {
                "symbol": f.symbol,
                "side": f.side.value,
                "quantity": dec(f.quantity),
                "price": dec(f.price),
                "fee": dec(f.fee),
                "slippage": dec(f.slippage),
                "executed_at": f.executed_at.isoformat(),
                "execution_id": str(f.execution_id) if f.execution_id else None,
            }
            for f in sorted(inp.fills, key=lambda x: (x.executed_at, x.symbol, x.side.value))
        ],
        "corporate_actions": [
            {
                "symbol": a.symbol,
                "kind": a.kind.value,
                "effective_date": a.effective_date.isoformat(),
                "amount": dec(a.amount),
            }
            for a in sorted(
                inp.corporate_actions, key=lambda x: (x.effective_date, x.symbol, x.kind.value)
            )
        ],
        "benchmark": (
            None
            if inp.benchmark is None
            else {
                "symbol": inp.benchmark.symbol,
                "period_date": inp.benchmark.period_date.isoformat(),
                "opening_price": dec(inp.benchmark.opening_price),
                "closing_price": dec(inp.benchmark.closing_price),
            }
        ),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
