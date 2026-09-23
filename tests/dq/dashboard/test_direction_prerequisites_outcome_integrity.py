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
    _PERIOD_PIN_COLUMNS,
    _period_version_pin,
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


# --- #4556: the accounting-period pin must materialise, not silently drop ---
#
# ``accounting_periods`` has never had a stored ``content_hash`` column (see
# 072_olympus_period_accounting.sql). The original select asked for one anyway,
# so PostgREST answered ``42703`` on every run, the caller caught it at DEBUG,
# and the tip-period pin was dropped. Before the fix both fields below are
# ``None``. The pin is now derived locally from the row identity.

_ACCOUNTING_ROW = {
    "id": "5b1f2a3c-9d4e-4f60-8a71-2c3d4e5f6071",
    "period_date": "2026-08-24",
    "status": "final",
    "policy_version_id": "0f9e8d7c-6b5a-4392-8170-6f5e4d3c2b1a",
    "recorded_at": "2026-08-24T21:05:00+00:00",
}


def test_accounting_period_pin_materialises_without_a_stored_content_hash() -> None:
    client = FakeSupabaseClient(canned_reads={"accounting_periods": [_ACCOUNTING_ROW]})

    snapshot = _snapshot(client)

    assert snapshot is not None
    # The load-bearing id used by the direction context compiler survives...
    assert snapshot.accounting_period_id is not None
    # ...and the version pin is now present rather than silently dropped.
    assert snapshot.accounting_period_content_hash is not None


def test_period_pin_columns_never_reference_content_hash() -> None:
    # The table has no such column; asking for it is a guaranteed 400.
    assert "content_hash" not in _PERIOD_PIN_COLUMNS
    assert "id" in _PERIOD_PIN_COLUMNS


def test_period_version_pin_is_deterministic_and_ignores_field_order() -> None:
    reordered = {
        "recorded_at": _ACCOUNTING_ROW["recorded_at"],
        "policy_version_id": _ACCOUNTING_ROW["policy_version_id"],
        "status": _ACCOUNTING_ROW["status"],
        "period_date": _ACCOUNTING_ROW["period_date"],
        "id": _ACCOUNTING_ROW["id"],
    }

    assert _period_version_pin(dict(_ACCOUNTING_ROW)) == _period_version_pin(reordered)
    assert _period_version_pin({}) is None
    assert _period_version_pin({"id": None}) is None
