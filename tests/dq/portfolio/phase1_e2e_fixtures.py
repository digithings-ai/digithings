"""Deterministic helpers for Integration Task 1.1 E2E (#2719)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

from digiquant.research.testing.simulator import (
    DEFAULT_RESPONSES,
    parse_phase_inputs,
    seed_supabase_client,
)
from digiquant.portfolio.models.forecast_calibration import (
    ForecastOutcome,
    OutcomeStatus,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)

from tests.dq.research.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

PHASE1_RUN_DATE = date(2026, 4, 26)
PRIOR_KNOWN_AT = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
LATE_KNOWN_AT = datetime(2099, 1, 1, 0, 0, tzinfo=UTC)
_REF_SESSION = date(2026, 2, 10)
_MAT_SESSION = date(2026, 3, 10)
_BASE_FORECAST_ID = UUID("11111111-1111-5111-8111-111111111111")

PHASE1_PIPELINE_PREFERENCES: dict[str, Any] = {
    "max_single_etf_pct": 100,
    "max_sector_pct": 100,
    "target_portfolio_vol": 1.0e6,
    "weight_increment_pct": 0,
    "min_conviction": 2.0,
}


def sample_forecast_terms_dict() -> dict[str, Any]:
    return {
        "horizon_sessions": 21,
        "half_life_sessions": 10,
        "bear_return": "-0.10",
        "base_return": "0.03",
        "bull_return": "0.15",
        "bear_probability": "0.25",
        "base_probability": "0.50",
        "bull_probability": "0.25",
        "thesis_valid_probability": "0.55",
        "raw_uncertainty": "medium",
        "evidence_ids": ["ev-phase1-e2e"],
        "counter_evidence_ids": [],
        "assumptions": ["integration-1.1"],
        "invalidation_rules": ["thesis-break"],
    }


def invalid_forecast_amendment_dict() -> dict[str, Any]:
    """Probabilities sum to 1.25 — must reject amendment and preserve base."""
    terms = sample_forecast_terms_dict()
    terms["bear_probability"] = "0.50"
    terms["base_probability"] = "0.50"
    terms["bull_probability"] = "0.25"
    return terms


@dataclass
class _MergingQuery(_FakeQuery):
    """Reads store ∪ canned so registry FK checks see prior INSERTs."""

    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._update_row is not None:
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        if self._delete:
            rows = self.store.get(self.table_name, [])
            removed = [r for r in rows if self._matches(r)]
            self.store[self.table_name] = [r for r in rows if not self._matches(r)]
            return _FakeResponse(data=removed)
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        rows = [r for r in merged if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class Phase1E2EFake(FakeSupabaseClient):
    """Fake Supabase client with merged reads for Phase 1 registry + ledger I/O."""

    def table(self, name: str) -> _MergingQuery:
        return _MergingQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )


def seed_phase1_client(
    canned_extras: dict[str, list[Any]] | None = None,
    *,
    replace_defaults: bool = False,
) -> Phase1E2EFake:
    base = seed_supabase_client(canned_extras, replace_defaults=replace_defaults)
    _coerce_price_history_dates(base.canned_reads)
    return Phase1E2EFake(store=dict(base.store), canned_reads=dict(base.canned_reads))


def _coerce_price_history_dates(canned_reads: dict[str, list[Any]]) -> None:
    """Polars ADV math compares ``date`` column to ``date`` — normalize seed rows."""
    rows = canned_reads.get("price_history")
    if not rows:
        return
    for row in rows:
        raw = row.get("date")
        if isinstance(raw, str):
            row["date"] = date.fromisoformat(raw)


def analyst_payload_override(*args: Any, **kwargs: Any) -> str:
    messages = kwargs.get("messages")
    if messages is None and args:
        messages = args[0]
    inputs = parse_phase_inputs(messages if isinstance(messages, list) else [])
    ticker = str(inputs.get("ticker", "AAPL"))
    payload = {
        **DEFAULT_RESPONSES["AnalystPayload"],
        "ticker": ticker,
        "conviction_score": 4,
        "stance": "buy",
        "forecast": sample_forecast_terms_dict(),
    }
    return json.dumps(payload)


def deliberation_analyst_amendment_override(amendment: dict[str, Any] | None):
    def _override(*args: Any, **kwargs: Any) -> str:
        body = dict(DEFAULT_RESPONSES["DeliberationAnalystTurn"])
        if amendment is not None:
            body["forecast_amendment"] = amendment
            body["revises_payload"] = True
        return json.dumps(body)

    return _override


def _session_snapshot(*, session: date, price: str = "100") -> SessionPriceSnapshot:
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=PRIOR_KNOWN_AT - timedelta(hours=6),
        known_at=PRIOR_KNOWN_AT - timedelta(hours=5),
    )


def resolved_outcome_row(*, salt: int = 0, known_at: datetime = PRIOR_KNOWN_AT) -> dict[str, Any]:
    mean = Decimal("0.04")
    realized = Decimal("0.06")
    residual = realized - mean
    eff_id = UUID(f"22222222-2222-5222-8222-{salt:012d}")
    draft: dict[str, Any] = {
        "base_forecast_id": str(_BASE_FORECAST_ID),
        "effective_forecast_id": str(eff_id),
        "ticker": f"T{salt:02d}",
        "horizon_sessions": 21,
        "reference_session": _REF_SESSION.isoformat(),
        "maturity_session": _MAT_SESSION.isoformat(),
        "reference_snapshot": _session_snapshot(session=_REF_SESSION).model_dump(mode="json"),
        "maturity_snapshot": _session_snapshot(session=_MAT_SESSION, price="106").model_dump(
            mode="json"
        ),
        "forecast_mean_return": str(mean),
        "realized_return": str(realized),
        "signed_residual": str(residual),
        "positive_label": True,
        "status": OutcomeStatus.RESOLVED.value,
        "unavailable_reason": None,
        "event_time": known_at.isoformat(),
        "known_at": known_at.isoformat(),
    }
    content_hash = forecast_outcome_content_hash(payload=draft)
    outcome_id = forecast_outcome_id(
        effective_forecast_id=eff_id,
        maturity_session=_MAT_SESSION,
        content_hash=content_hash,
    )
    outcome = ForecastOutcome(
        outcome_id=outcome_id,
        content_hash=content_hash,
        base_forecast_id=_BASE_FORECAST_ID,
        effective_forecast_id=eff_id,
        ticker=f"T{salt:02d}",
        horizon_sessions=21,
        reference_session=_REF_SESSION,
        maturity_session=_MAT_SESSION,
        reference_snapshot=_session_snapshot(session=_REF_SESSION),
        maturity_snapshot=_session_snapshot(session=_MAT_SESSION, price="106"),
        forecast_mean_return=mean,
        realized_return=realized,
        signed_residual=residual,
        positive_label=True,
        status=OutcomeStatus.RESOLVED,
        unavailable_reason=None,
        event_time=known_at,
        known_at=known_at,
    )
    return outcome.model_dump(mode="json")


def mature_cohort_outcome_rows(*, count: int = 3) -> list[dict[str, Any]]:
    return [resolved_outcome_row(salt=i) for i in range(count)]


def sized_book_weights(sized_book: dict[str, Any] | None) -> dict[str, float]:
    if not sized_book:
        return {}
    return {
        str(row["ticker"]): float(row["target_pct"])
        for row in sized_book.get("recommended_portfolio") or []
        if row.get("ticker")
    }
