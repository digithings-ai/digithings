"""Writer/reader tests for the prospective forecast registry (#2663 / WP4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import pytest
from digiquant.olympus.atlas import forecast_registry as fr
from digiquant.olympus.atlas.state import AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.models.forecast import (
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    forecast_terms_content_hash,
    materialize_forecast_amendment,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

pytestmark = pytest.mark.unit

TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
CUTOFF = TS + timedelta(hours=1)
RUN_ID = "run-wp46-1"


@dataclass
class _MergingQuery(_FakeQuery):
    """Reads from store ∪ canned so exact retries see prior INSERTs."""

    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            if self.table_name in (
                fr.ASSESSMENTS,
                fr.AMENDMENTS,
                fr.CALIBRATIONS,
                fr.CALIBRATED_FORECASTS,
            ):
                raise AssertionError("upsert is forbidden on the forecast registry")
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._update_row is not None:
            if self.table_name in (
                fr.ASSESSMENTS,
                fr.AMENDMENTS,
                fr.CALIBRATIONS,
                fr.CALIBRATED_FORECASTS,
            ):
                raise AssertionError("update is forbidden on the forecast registry")
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        if self._delete:
            if self.table_name in (
                fr.ASSESSMENTS,
                fr.AMENDMENTS,
                fr.CALIBRATIONS,
                fr.CALIBRATED_FORECASTS,
            ):
                raise AssertionError("delete is forbidden on the forecast registry")
            rows = self.store.get(self.table_name, [])
            removed = [r for r in rows if self._matches(r)]
            self.store[self.table_name] = [r for r in rows if not self._matches(r)]
            return _FakeResponse(data=removed)
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for row in merged:
            key = str(
                row.get("forecast_id")
                or row.get("amendment_id")
                or row.get("calibration_id")
                or row.get("calibrated_forecast_id")
                or row.get("id")
                or id(row)
            )
            if key in seen:
                continue
            seen.add(key)
            if self._matches(row):
                rows.append(row)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class RegistryFake(FakeSupabaseClient):
    fail_table: str | None = None

    def table(self, name: str) -> _MergingQuery:
        q = _MergingQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )
        if self.fail_table == name:

            def boom(row: dict[str, Any] | list[dict[str, Any]]) -> _MergingQuery:
                raise RuntimeError(f"simulated {name} outage")

            q.insert = boom  # type: ignore[method-assign]
        return q


def _terms(**over: Any) -> ForecastTerms:
    base = dict(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return=Decimal("-0.10"),
        base_return=Decimal("0.04"),
        bull_return=Decimal("0.15"),
        bear_probability=Decimal("0.25"),
        base_probability=Decimal("0.50"),
        bull_probability=Decimal("0.25"),
        thesis_valid_probability=Decimal("0.60"),
        raw_uncertainty=RawUncertainty.MEDIUM,
    )
    base.update(over)
    return ForecastTerms(**base)


def _assessment(*, ticker: str = "SPY", content_hash: str | None = None) -> ForecastAssessment:
    terms = _terms()
    ch = content_hash or forecast_terms_content_hash(terms)
    from digiquant.olympus.hermes.models.forecast import forecast_assessment_id

    return ForecastAssessment(
        forecast_id=forecast_assessment_id(ticker=ticker, source_run_id=RUN_ID, content_hash=ch),
        ticker=ticker,
        terms=terms,
        source_run_id=RUN_ID,
        provider_invocation_id="inv-1",
        prompt_version="pv-1",
        artifact_version="av-1",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.OBSERVED,
            price=Decimal("100"),
            observed_at=TS,
        ),
        effective_at=TS,
        known_at=TS,
        content_hash=ch,
    )


def test_exact_retry_is_idempotent_noop() -> None:
    client = RegistryFake()
    assessment = _assessment()
    first = fr.persist_forecast_lineage(client=client, assessments=[assessment])
    second = fr.persist_forecast_lineage(client=client, assessments=[assessment])
    assert first.assessments_written == 1
    assert second.assessments_written == 0
    assert second.assessments_skipped == 1
    assert len(client.store[fr.ASSESSMENTS]) == 1


def test_content_conflict_same_id_different_hash() -> None:
    client = RegistryFake()
    a1 = _assessment()
    fr.persist_forecast_lineage(client=client, assessments=[a1])
    # Force same forecast_id with a different hash by mutating the stored row's hash
    # then attempting a re-write with the real assessment after poisoning — instead
    # plant a conflicting row directly.
    client.store[fr.ASSESSMENTS][0]["content_hash"] = "0" * 64
    result = fr.persist_forecast_lineage(client=client, assessments=[a1])
    assert result.degraded_reason == "content_conflict"
    assert result.conflicts
    assert len(client.store[fr.ASSESSMENTS]) == 1


def test_amendment_requires_persisted_base() -> None:
    client = RegistryFake()
    base = _assessment()
    amended_terms = _terms(base_return=Decimal("0.05"))
    amendment = materialize_forecast_amendment(
        base=base,
        terms=amended_terms,
        reason="challenge",
        source_run_id=RUN_ID,
        provider_invocation_id="h6:SPY:run",
        effective_at=TS,
        known_at=TS,
    )
    result = fr.persist_forecast_lineage(client=client, amendments=[amendment])
    assert result.degraded_reason is not None
    assert "missing base" in (result.degraded_reason or "")


def test_amendment_reason_over_sql_cap_is_truncated() -> None:
    """079 `olympus_forecast_amendments_reason_check` is length 1..2000.

    House GHA 33426508863: H6 BITO amendment reason exceeded the check, so the
    registry insert 23514'd (`h9 forecast registry degraded`) while the book was
    retained. Truncate at the write boundary — content_hash is over terms, not reason.
    """
    client = RegistryFake()
    base = _assessment()
    long_reason = "The PM's three challenges are accepted as substantive and force " + ("x" * 2500)
    amendment = materialize_forecast_amendment(
        base=base,
        terms=_terms(base_return=Decimal("0.05")),
        reason=long_reason,
        source_run_id=RUN_ID,
        provider_invocation_id="h6:BITO:run",
        effective_at=TS,
        known_at=TS,
    )
    result = fr.persist_forecast_lineage(client=client, assessments=[base], amendments=[amendment])
    assert result.ok
    stored = client.store[fr.AMENDMENTS][0]["reason"]
    assert len(stored) == fr.AMENDMENT_REASON_MAX_LEN
    assert stored == long_reason[: fr.AMENDMENT_REASON_MAX_LEN]


def test_persist_base_then_amendment() -> None:
    client = RegistryFake()
    base = _assessment()
    amendment = materialize_forecast_amendment(
        base=base,
        terms=_terms(base_return=Decimal("0.05")),
        reason="challenge",
        source_run_id=RUN_ID,
        provider_invocation_id="h6:SPY:run",
        effective_at=TS,
        known_at=TS,
    )
    result = fr.persist_forecast_lineage(client=client, assessments=[base], amendments=[amendment])
    assert result.ok
    assert result.assessments_written == 1
    assert result.amendments_written == 1


def test_cutoff_read_hides_late_known() -> None:
    client = RegistryFake()
    assessment = _assessment()
    fr.persist_forecast_lineage(client=client, assessments=[assessment])
    early = fr.get_forecast_assessment(
        client=client,
        forecast_id=assessment.forecast_id,
        knowledge_cutoff_at=TS - timedelta(seconds=1),
    )
    assert early is None
    ok = fr.get_forecast_assessment(
        client=client,
        forecast_id=assessment.forecast_id,
        knowledge_cutoff_at=CUTOFF,
    )
    assert ok is not None
    assert ok.forecast_id == assessment.forecast_id


def test_collect_and_persist_from_state() -> None:
    client = RegistryFake()
    assessment = _assessment()
    amendment = materialize_forecast_amendment(
        base=assessment,
        terms=_terms(base_return=Decimal("0.06")),
        reason="h6",
        source_run_id=RUN_ID,
        provider_invocation_id="h6:SPY:x",
        effective_at=TS,
        known_at=TS,
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=TS.date(),
        baseline_date=TS.date(),
        phase_hermes=PhaseHermesState(
            asset_analysts={
                "SPY": {
                    "ticker": "SPY",
                    "forecast_assessment": assessment.model_dump(mode="json"),
                }
            },
            deliberation_summaries={
                "SPY": {
                    "ticker": "SPY",
                    "forecast_amendment": amendment.model_dump(mode="json"),
                }
            },
        ),
    )
    result = fr.persist_forecast_lineage_from_state(client=client, state=state)
    assert result.ok
    assert result.assessments_written == 1
    assert result.amendments_written == 1


def test_insert_only_never_upsert() -> None:
    client = RegistryFake()
    assessment = _assessment()
    fr.persist_forecast_lineage(client=client, assessments=[assessment])
    assert all("_on_conflict" not in r for rows in client.store.values() for r in rows)
