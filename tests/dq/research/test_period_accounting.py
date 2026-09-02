"""Unit tests for Olympus event-boundary period accounting (#2596, Task 3.1).

Golden fixtures: hold, add, trim, exit, cash, multiple fills, open gap, costs,
dividend/split policy, missing marks, stale marks, benchmark mismatch, exact retry,
and non-zero residual failure. All final periods must satisfy the core identities.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from digiquant.olympus.accounting import (
    AccountingPeriod,
    AccountingPolicy,
    BenchmarkBoundary,
    CorporateAction,
    CorporateActionKind,
    DividendPolicy,
    FillSide,
    MarkObservation,
    OpeningHolding,
    PeriodAccountingInput,
    PeriodFill,
    PeriodStatus,
    QualityReason,
    SplitPolicy,
    compute_period,
    period_id_for_input,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

PERIOD = date(2026, 8, 25)
POLICY = AccountingPolicy(policy_version_id="accounting-v1")


def _ts(hour: int = 14, minute: int = 30, day: date | None = None) -> datetime:
    d = day or PERIOD
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC)


def _mark(
    symbol: str,
    price: str,
    *,
    as_of: date | None = None,
    observed_at: datetime | None = None,
) -> MarkObservation:
    return MarkObservation(
        symbol=symbol,
        price=Decimal(price),
        as_of=as_of or PERIOD,
        observed_at=observed_at or _ts(21, 0),
    )


def _assert_identities(period: AccountingPeriod) -> None:
    e0 = period.opening_equity
    e1 = period.closing_equity
    net = sum((t.net_pnl for t in period.ticker_results), Decimal("0"))
    assert e1 == e0 + net + period.cash_pnl
    marked = sum(
        (h.market_value for h in period.closing_holdings if h.market_value is not None),
        Decimal("0"),
    )
    assert e1 == period.closing_cash + marked
    if e0 > 0 and period.cash_contribution is not None:
        contrib = sum(
            (t.contribution for t in period.ticker_results if t.contribution is not None),
            Decimal("0"),
        )
        assert contrib + period.cash_contribution == (e1 - e0) / e0


def test_hold_mark_to_market_reconciles() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("40000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "110"),),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.opening_equity == Decimal("50000")
    assert out.closing_equity == Decimal("51000")
    assert out.ticker_results[0].net_pnl == Decimal("1000")
    assert out.residual == Decimal("0")
    _assert_identities(out)


def test_add_buy_open_gap() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("100000"),
        opening_holdings=(),
        opening_marks=(),
        closing_marks=(_mark("NVDA", "120"),),
        fills=(
            PeriodFill(
                symbol="NVDA",
                side=FillSide.BUY,
                quantity=Decimal("50"),
                price=Decimal("100"),
                executed_at=_ts(9, 30),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert QualityReason.OPEN_GAP in out.ticker_results[0].quality_reasons
    assert out.closing_cash == Decimal("95000")
    assert out.closing_equity == Decimal("101000")
    _assert_identities(out)


def test_trim_partial_sell() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("10000"),
        opening_holdings=(OpeningHolding(symbol="MSFT", quantity=Decimal("100")),),
        opening_marks=(_mark("MSFT", "200", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("MSFT", "210"),),
        fills=(
            PeriodFill(
                symbol="MSFT",
                side=FillSide.SELL,
                quantity=Decimal("40"),
                price=Decimal("205"),
                executed_at=_ts(10, 0),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.ticker_results[0].closing_quantity == Decimal("60")
    _assert_identities(out)


def test_exit_full_sell() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="META", quantity=Decimal("10")),),
        opening_marks=(_mark("META", "500", as_of=date(2026, 8, 24)),),
        closing_marks=(),
        fills=(
            PeriodFill(
                symbol="META",
                side=FillSide.SELL,
                quantity=Decimal("10"),
                price=Decimal("520"),
                executed_at=_ts(11, 0),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.closing_holdings == ()
    assert out.ticker_results[0].net_pnl == Decimal("200")
    assert out.closing_cash == Decimal("5200")
    _assert_identities(out)


def test_cash_only_book() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("100000"),
        opening_holdings=(),
        opening_marks=(),
        closing_marks=(),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.opening_equity == out.closing_equity == Decimal("100000")
    assert out.net_pnl_total == Decimal("0")
    _assert_identities(out)


def test_multiple_fills_ordered() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("20000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("10")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "105"),),
        fills=(
            PeriodFill(
                symbol="AAPL",
                side=FillSide.BUY,
                quantity=Decimal("5"),
                price=Decimal("102"),
                executed_at=_ts(15, 0),
            ),
            PeriodFill(
                symbol="AAPL",
                side=FillSide.BUY,
                quantity=Decimal("5"),
                price=Decimal("101"),
                executed_at=_ts(10, 0),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.ticker_results[0].closing_quantity == Decimal("20")
    _assert_identities(out)


def test_costs_reduce_net_pnl() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("10000"),
        opening_holdings=(),
        closing_marks=(_mark("SPY", "500"),),
        fills=(
            PeriodFill(
                symbol="SPY",
                side=FillSide.BUY,
                quantity=Decimal("10"),
                price=Decimal("500"),
                fee=Decimal("5"),
                slippage=Decimal("2"),
                executed_at=_ts(9, 30),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    row = out.ticker_results[0]
    assert row.fees == Decimal("5")
    assert row.slippage == Decimal("2")
    assert row.net_pnl == row.gross_pnl - Decimal("7")
    assert out.closing_cash == Decimal("10000") - Decimal("5000") - Decimal("7")
    _assert_identities(out)


def test_dividend_to_cash_policy() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("1000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "100"),),
        corporate_actions=(
            CorporateAction(
                symbol="AAPL",
                kind=CorporateActionKind.DIVIDEND_CASH,
                effective_date=PERIOD,
                amount=Decimal("0.25"),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.cash_pnl == Decimal("25")
    assert out.closing_cash == Decimal("1025")
    _assert_identities(out)


def test_dividend_ignore_policy_flags_reason() -> None:
    policy = AccountingPolicy(
        policy_version_id="accounting-v1-ignore-div",
        dividend_policy=DividendPolicy.IGNORE,
    )
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=policy,
        opening_cash=Decimal("1000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "100"),),
        corporate_actions=(
            CorporateAction(
                symbol="AAPL",
                kind=CorporateActionKind.DIVIDEND_CASH,
                effective_date=PERIOD,
                amount=Decimal("0.25"),
            ),
        ),
    )
    out = compute_period(inp)
    assert QualityReason.CORPORATE_ACTION_IGNORED in out.quality_reasons
    assert out.cash_pnl == Decimal("0")
    assert out.status is PeriodStatus.ESTIMATED


def test_split_adjusts_quantity() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="TSLA", quantity=Decimal("10")),),
        opening_marks=(_mark("TSLA", "200", as_of=date(2026, 8, 24)),),
        # Post-split mark: half the pre-split price for a 2-for-1.
        closing_marks=(_mark("TSLA", "100"),),
        corporate_actions=(
            CorporateAction(
                symbol="TSLA",
                kind=CorporateActionKind.SPLIT,
                effective_date=PERIOD,
                amount=Decimal("2"),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.ticker_results[0].closing_quantity == Decimal("20")
    assert out.closing_equity == Decimal("2000")
    assert out.net_pnl_total == Decimal("0")
    _assert_identities(out)


def test_split_ignore_policy() -> None:
    policy = AccountingPolicy(
        policy_version_id="accounting-v1-ignore-split",
        split_policy=SplitPolicy.IGNORE,
    )
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=policy,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="TSLA", quantity=Decimal("10")),),
        opening_marks=(_mark("TSLA", "200", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("TSLA", "200"),),
        corporate_actions=(
            CorporateAction(
                symbol="TSLA",
                kind=CorporateActionKind.SPLIT,
                effective_date=PERIOD,
                amount=Decimal("2"),
            ),
        ),
    )
    out = compute_period(inp)
    assert QualityReason.CORPORATE_ACTION_IGNORED in out.quality_reasons
    assert out.ticker_results[0].closing_quantity == Decimal("10")


def test_missing_closing_mark_is_incomplete() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("10")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.INCOMPLETE
    assert QualityReason.MISSING_CLOSING_MARK in out.quality_reasons
    assert out.status is not PeriodStatus.FINAL


def test_stale_closing_mark_is_estimated() -> None:
    stale = _mark(
        "AAPL",
        "110",
        observed_at=_ts(21, 0, day=date(2026, 8, 20)),
    )
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("10")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(stale,),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.ESTIMATED
    assert QualityReason.STALE_CLOSING_MARK in out.quality_reasons


def test_benchmark_mismatch_fails() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("100000"),
        benchmark=BenchmarkBoundary(
            symbol="SPY",
            period_date=date(2026, 8, 24),
            opening_price=Decimal("500"),
            closing_price=Decimal("505"),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FAILED
    assert QualityReason.BENCHMARK_BOUNDARY_MISMATCH in out.quality_reasons


def test_exact_retry_same_period_id() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("50000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("10")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "101"),),
    )
    a = compute_period(inp)
    b = compute_period(inp)
    assert a.id == b.id == period_id_for_input(inp)
    assert a.model_dump() == b.model_dump()


def test_non_zero_residual_never_final() -> None:
    """Safety net: unexplained residual must never publish as final.

    The pure engine reconciles by construction; residual is the gate for future
    persistence/replay corruption. Missing opening marks stay non-final as well.
    """
    from digiquant.olympus.accounting.engine import _resolve_status

    assert (
        _resolve_status([QualityReason.RESIDUAL_EXCEEDED], Decimal("1.00"), Decimal("0.01"))
        is PeriodStatus.FAILED
    )

    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=AccountingPolicy(
            policy_version_id="accounting-v1-tight",
            absolute_tolerance=Decimal("0.01"),
            relative_tolerance=Decimal("0"),
        ),
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("10")),),
        opening_marks=(),
        closing_marks=(_mark("AAPL", "110"),),
    )
    out = compute_period(inp)
    assert out.status is not PeriodStatus.FINAL
    assert QualityReason.MISSING_OPENING_MARK in out.quality_reasons


def test_over_sell_negative_quantity_fails() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("0"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("5")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(),
        fills=(
            PeriodFill(
                symbol="AAPL",
                side=FillSide.SELL,
                quantity=Decimal("10"),
                price=Decimal("100"),
                executed_at=_ts(10, 0),
            ),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FAILED
    assert QualityReason.NEGATIVE_QUANTITY in out.quality_reasons


def test_mark_requires_utc() -> None:
    with pytest.raises(ValidationError):
        MarkObservation(
            symbol="AAPL",
            price=Decimal("100"),
            as_of=PERIOD,
            observed_at=datetime(2026, 8, 25, 21, 0),  # noqa: DTZ001 — intentional naive
        )


def test_duplicate_opening_holding_rejected() -> None:
    with pytest.raises(ValidationError):
        PeriodAccountingInput(
            period_date=PERIOD,
            policy=POLICY,
            opening_cash=Decimal("0"),
            opening_holdings=(
                OpeningHolding(symbol="AAPL", quantity=Decimal("1")),
                OpeningHolding(symbol="AAPL", quantity=Decimal("2")),
            ),
        )


def test_aligned_benchmark_return() -> None:
    inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("100000"),
        benchmark=BenchmarkBoundary(
            symbol="SPY",
            period_date=PERIOD,
            opening_price=Decimal("500"),
            closing_price=Decimal("510"),
        ),
    )
    out = compute_period(inp)
    assert out.status is PeriodStatus.FINAL
    assert out.benchmark_return == Decimal("0.02")
