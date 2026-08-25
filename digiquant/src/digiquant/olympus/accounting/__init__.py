"""Olympus event-boundary period accounting (#2596, Phase 0 Task 3.1).

Pure Decimal/Polars contracts and engine. Persistence and reader cutover are Tasks 3.2–3.4.
Portfolio/accounting tables are user-private — never grant public base-table access.
"""

from digiquant.olympus.accounting.engine import compute_period, period_id_for_input
from digiquant.olympus.accounting.models import (
    AccountingPeriod,
    AccountingPolicy,
    BenchmarkBoundary,
    ClosingHolding,
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
    TickerPeriodResult,
)

__all__ = [
    "AccountingPeriod",
    "AccountingPolicy",
    "BenchmarkBoundary",
    "ClosingHolding",
    "CorporateAction",
    "CorporateActionKind",
    "DividendPolicy",
    "FillSide",
    "MarkObservation",
    "OpeningHolding",
    "PeriodAccountingInput",
    "PeriodFill",
    "PeriodStatus",
    "QualityReason",
    "SplitPolicy",
    "TickerPeriodResult",
    "compute_period",
    "period_id_for_input",
]
