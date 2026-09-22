"""#4298 caller guard: direction prerequisites must fail loud on a stale persisted digest.

The reader (``list_resolved_outcomes_as_of``) raises
``ForecastOutcomeIntegrityError``; this caller used to catch ``Exception``,
log at DEBUG and return ``None``, neutralizing the fail-loud contract. These
tests exercise the *caller*, not the reader in isolation.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from digiquant.dashboard.research_retrieval.direction_decision_context import (
    DirectionPrerequisiteSnapshot,
)
from digiquant.dashboard.research_retrieval.direction_prerequisites import (
    build_direction_prerequisite_snapshot,
)
from digiquant.research import forecast_outcomes as fo

from tests.dq.research.test_forecast_outcome_hash_ingress import (
    _build_outcome,
    _postgrest_numeric_roundtrip,
    _stale_row,
)
from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

CUTOFF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
RUN_DATE = date(2026, 8, 25)


def _snapshot(client: FakeSupabaseClient) -> DirectionPrerequisiteSnapshot | None:
    return build_direction_prerequisite_snapshot(
        client=client,
        run_date=RUN_DATE,
        knowledge_cutoff_at=CUTOFF,
        research_state_pin=None,
    )


def test_stale_outcome_row_fails_loud_instead_of_none() -> None:
    client = FakeSupabaseClient(canned_reads={fo.OUTCOMES: [_stale_row()]})

    with pytest.raises(
        fo.ForecastOutcomeIntegrityError,
        match="repair_forecast_outcome_hashes",
    ):
        _snapshot(client)


def test_healthy_outcome_row_still_pins_matured_ids() -> None:
    row = _postgrest_numeric_roundtrip(fo._outcome_row(_build_outcome()))
    client = FakeSupabaseClient(canned_reads={fo.OUTCOMES: [row]})

    snapshot = _snapshot(client)

    assert snapshot is not None
    # The matured cohort is pinned, not silently dropped.
    assert snapshot.matured_forecast_outcome_ids


def test_transient_outcome_load_failure_still_degrades() -> None:
    class _BrokenClient:
        def table(self, _name: str) -> object:
            raise RuntimeError("transient backend failure")

    # Non-integrity failures keep the pre-existing fail-soft (snapshot None),
    # so the guard is narrow: only the named integrity error is made loud.
    assert _snapshot(_BrokenClient()) is None  # type: ignore[arg-type]
