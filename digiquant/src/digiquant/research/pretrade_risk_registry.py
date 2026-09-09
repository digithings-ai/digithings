"""Private append-only PreTradeRiskReport registry (#2754 / WP9.4).

Persists immutable :class:`~digiquant.portfolio.allocation_contracts.PreTradeRiskReport`
rows from migration ``083_olympus_pretrade_risk_reports.sql``.

**Exact retry:** same ``report_id`` + same ``report_content_hash`` is a no-op.
**Content conflict:** same ``report_id`` + different hash raises
:class:`PreTradeRiskRegistryConflict` — never UPDATE.
**H9 boundary:** validation lives in ``portfolio.writers.commit_io``; this module
only appends. H9 never imports report builders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import (
    Any,  # score:allow untyped any — duck-typed Supabase client / row dicts
)
from uuid import UUID, uuid5

from digiquant.portfolio.allocation_contracts import PreTradeRiskReport
from digiquant.research.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)

REPORTS = "olympus_pretrade_risk_reports"

# Stable namespace for PreTradeRiskReport UUID5 identity. Do not change — existing
# rows and H9 manifests key on report_id derived from content hash.
_PRETRADE_RISK_REPORT_ID_NAMESPACE = UUID("d4e5f6a7-b8c9-4012-8def-0123456789ab")


class PreTradeRiskRegistryConflict(RuntimeError):
    """Same identity already stored with a different content hash."""


class PreTradeRiskRegistryError(RuntimeError):
    """Registry persistence refused or left an inconsistent state."""


class _WriteKind(StrEnum):
    WRITTEN = "written"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PreTradeRiskRegistryWriteResult:
    """Outcome of one :func:`persist_pretrade_risk_report` call."""

    reports_written: int = 0
    reports_skipped: int = 0
    report_id: str | None = None
    report_content_hash: str | None = None
    degraded_reason: str | None = None
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.degraded_reason is None and not self.conflicts


def pretrade_risk_report_id(*, content_hash: str) -> UUID:
    """Deterministic UUID5 for a hash-bound pre-trade risk report."""
    return uuid5(_PRETRADE_RISK_REPORT_ID_NAMESPACE, content_hash)


def _insert(*, client: SupabaseClient, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client.table(table).insert(rows).execute()


def _fetch_by_id(
    *,
    client: SupabaseClient,
    table: str,
    id_column: str,
    row_id: UUID | str,
) -> dict[str, Any] | None:
    resp = client.table(table).select("*").eq(id_column, str(row_id)).limit(1).execute()
    rows = list(getattr(resp, "data", None) or [])
    return rows[0] if rows else None


def _report_row(
    *,
    report: PreTradeRiskReport,
    report_id: UUID,
    source_run_id: str,
    ledger_commit_id: UUID | None,
) -> dict[str, Any]:
    return {
        "report_id": str(report_id),
        "source_run_id": source_run_id,
        "session_date": report.session_date.isoformat()
        if isinstance(report.session_date, date)
        else str(report.session_date),
        "status": report.status.value,
        "unavailable_reason": report.unavailable_reason,
        "report_content_hash": report.report_content_hash,
        "allocation_input_bundle_hash": report.allocation_input_bundle_hash,
        "final_book_weights_fingerprint": report.final_book_weights_fingerprint,
        "ledger_commit_id": str(ledger_commit_id) if ledger_commit_id is not None else None,
        "report_body": report.model_dump(mode="json"),
    }


def persist_pretrade_risk_report(
    *,
    client: SupabaseClient,
    report: PreTradeRiskReport,
    source_run_id: str,
    ledger_commit_id: UUID | None = None,
) -> PreTradeRiskRegistryWriteResult:
    """Append one hash-bound report. Exact retry skips; content conflict raises."""
    report_id = pretrade_risk_report_id(content_hash=report.report_content_hash)
    existing = _fetch_by_id(
        client=client,
        table=REPORTS,
        id_column="report_id",
        row_id=report_id,
    )
    if existing is not None:
        existing_hash = str(existing.get("report_content_hash") or "")
        if existing_hash == report.report_content_hash:
            return PreTradeRiskRegistryWriteResult(
                reports_skipped=1,
                report_id=str(report_id),
                report_content_hash=report.report_content_hash,
            )
        raise PreTradeRiskRegistryConflict(
            f"report_id {report_id} exists with different report_content_hash"
        )
    _insert(
        client=client,
        table=REPORTS,
        rows=[
            _report_row(
                report=report,
                report_id=report_id,
                source_run_id=source_run_id,
                ledger_commit_id=ledger_commit_id,
            )
        ],
    )
    return PreTradeRiskRegistryWriteResult(
        reports_written=1,
        report_id=str(report_id),
        report_content_hash=report.report_content_hash,
    )


__all__ = [
    "REPORTS",
    "PreTradeRiskRegistryConflict",
    "PreTradeRiskRegistryError",
    "PreTradeRiskRegistryWriteResult",
    "persist_pretrade_risk_report",
    "pretrade_risk_report_id",
]
