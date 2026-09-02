"""Olympus event-boundary period accounting (#2596 / #2597, Phase 0 Tasks 3.1–3.2).

Pure Decimal/Polars contracts and engine plus append-only persistence. Curated public
views are Task 3.4. Portfolio/accounting tables are user-private — never grant public
base-table access.
"""

from digiquant.olympus.accounting.engine import compute_period, period_id_for_input
from digiquant.olympus.accounting.io import (
    AccountingPersistError,
    PersistResult,
    contribution_row_id,
    holding_row_id,
    period_children_complete,
    period_day_return_pct,
    period_head,
    persist_period,
    select_final_period,
)
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
    "AccountingPersistError",
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
    "PersistResult",
    "QualityReason",
    "SplitPolicy",
    "TickerPeriodResult",
    "compute_period",
    "contribution_row_id",
    "holding_row_id",
    "period_children_complete",
    "period_day_return_pct",
    "period_head",
    "period_id_for_input",
    "persist_period",
    "select_final_period",
]
