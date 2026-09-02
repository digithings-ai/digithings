"""Writer/reader tests for the H8 risk policy snapshot registry (#2698 / WP6.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

import polars as pl
import pytest
from digiquant.research import risk_policy_registry as rpr
from digiquant.research.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    PhaseHermesState,
    PriorContext,
)
from digiquant.portfolio.h8_risk_snapshots import resolve_h8_risk_artifacts

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

pytestmark = pytest.mark.unit

TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
CUTOFF = TS + timedelta(hours=1)
RUN_DATE = date(2026, 8, 25)
RUN_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


@dataclass
class _MergingQuery(_FakeQuery):
    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            if self.table_name in (rpr.POLICIES, rpr.SNAPSHOTS, rpr.RUN_REFS):
                raise AssertionError("upsert is forbidden on the risk policy registry")
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._update_row is not None:
            if self.table_name in (rpr.POLICIES, rpr.SNAPSHOTS, rpr.RUN_REFS):
                raise AssertionError("update is forbidden on the risk policy registry")
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        if self._delete:
            if self.table_name in (rpr.POLICIES, rpr.SNAPSHOTS, rpr.RUN_REFS):
                raise AssertionError("delete is forbidden on the risk policy registry")
            rows = self.store.get(self.table_name, [])
            removed = [r for r in rows if self._matches(r)]
            self.store[self.table_name] = [r for r in rows if not self._matches(r)]
            return _FakeResponse(data=removed)
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        rows = [r for r in merged if self._matches(r)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class RiskRegistryFake(FakeSupabaseClient):
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


def _artifacts():
    corr = pl.DataFrame({"a": ["SPY", "TLT"], "b": ["TLT", "SPY"], "corr": [0.5, 0.5]})
    state = AtlasResearchState(
        run_id=RUN_ID,
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 8, 24),
        knowledge_cutoff_at=TS,
        prior_context=PriorContext(),
        config=AtlasConfigBundle(preferences={}),
    )
    return resolve_h8_risk_artifacts(state=state, pm_tickers=["SPY", "TLT"], corr=corr)


def _state_with_artifacts() -> AtlasResearchState:
    bundle = _artifacts()
    return AtlasResearchState(
        run_id=RUN_ID,
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 8, 24),
        knowledge_cutoff_at=TS,
        prior_context=PriorContext(),
        phase_hermes=PhaseHermesState(
            risk_policy=bundle.policy.model_dump(mode="json"),
            covariance_snapshot=bundle.covariance_snapshot.model_dump(mode="json"),
        ),
    )


def test_persist_writes_policy_snapshot_and_run_ref() -> None:
    client = RiskRegistryFake()
    bundle = _artifacts()
    result = rpr.persist_h8_risk_snapshots(
        client=client,
        source_run_id=str(RUN_ID),
        run_date=RUN_DATE,
        policy=bundle.policy,
        snapshot=bundle.covariance_snapshot,
    )
    assert result.ok
    assert result.policies_written == 1
    assert result.snapshots_written == 1
    assert result.run_refs_written == 1
    assert len(client.store[rpr.POLICIES]) == 1
    assert len(client.store[rpr.SNAPSHOTS]) == 1
    assert len(client.store[rpr.RUN_REFS]) == 1


def test_exact_retry_skips() -> None:
    client = RiskRegistryFake()
    bundle = _artifacts()
    first = rpr.persist_h8_risk_snapshots(
        client=client,
        source_run_id=str(RUN_ID),
        run_date=RUN_DATE,
        policy=bundle.policy,
        snapshot=bundle.covariance_snapshot,
    )
    second = rpr.persist_h8_risk_snapshots(
        client=client,
        source_run_id=str(RUN_ID),
        run_date=RUN_DATE,
        policy=bundle.policy,
        snapshot=bundle.covariance_snapshot,
    )
    assert first.ok and second.ok
    assert second.policies_skipped == 1
    assert second.snapshots_skipped == 1
    assert second.run_refs_skipped == 1


def test_get_risk_policy_respects_cutoff() -> None:
    client = RiskRegistryFake()
    bundle = _artifacts()
    rpr.persist_h8_risk_snapshots(
        client=client,
        source_run_id=str(RUN_ID),
        run_date=RUN_DATE,
        policy=bundle.policy,
        snapshot=bundle.covariance_snapshot,
    )
    assert (
        rpr.get_risk_policy(
            client=client,
            policy_id=bundle.policy.policy_id,
            knowledge_cutoff_at=CUTOFF,
        )
        is not None
    )
    assert (
        rpr.get_risk_policy(
            client=client,
            policy_id=bundle.policy.policy_id,
            knowledge_cutoff_at=bundle.policy.effective_at - timedelta(hours=1),
        )
        is None
    )


def test_persist_from_state_empty_is_ok() -> None:
    client = RiskRegistryFake()
    state = AtlasResearchState(
        run_id=RUN_ID,
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 8, 24),
    )
    result = rpr.persist_h8_risk_snapshots_from_state(client=client, state=state)
    assert result.ok
    assert result.policies_written == 0


def test_persist_from_state_round_trip() -> None:
    client = RiskRegistryFake()
    result = rpr.persist_h8_risk_snapshots_from_state(client=client, state=_state_with_artifacts())
    assert result.ok
    assert result.run_refs_written == 1
