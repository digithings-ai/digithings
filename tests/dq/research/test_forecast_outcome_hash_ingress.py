"""Forecast outcome hash ingress across the Postgres ``numeric`` boundary (#4298).

Kept out of ``test_forecast_outcomes.py`` so the #4296 writer PR (#4309) and this
#4298 ingress fix can land independently.

The bug: ``forecast_outcomes`` stores ``forecast_mean_return`` /
``realized_return`` / ``signed_residual`` in Postgres ``numeric`` columns. Postgres
does not preserve trailing zeros, so a value written as ``"0.03250000"`` reads back
through PostgREST as the JSON number ``0.0325`` (a Python float) and re-``str()``s to
``"0.0325"``. Hashing the raw spelling therefore diverges between write and read,
and the daily house reflect soft-skipped the row on ``ValidationError``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from digiquant.portfolio.models.forecast import (
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    forecast_assessment_id,
    forecast_terms_content_hash,
)
from digiquant.portfolio.models.forecast_calibration import (
    ForecastOutcome,
    SessionPriceSnapshot,
    forecast_outcome_content_hash,
    forecast_outcome_id,
)
from digiquant.research import forecast_outcomes as fo
from pydantic import ValidationError

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

TS = datetime(2026, 7, 15, 20, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
REF_SESSION = date(2026, 7, 15)
MAT_SESSION = date(2026, 8, 13)
# Non-quantized ``scenario_mean_return``: the spelling that loses trailing zeros.
MEAN = Decimal("0.0325")
REALIZED = Decimal("0.06000000")
RESIDUAL = Decimal("0.02750000")


def _assessment() -> ForecastAssessment:
    terms = ForecastTerms(
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
    content_hash = forecast_terms_content_hash(terms)
    return ForecastAssessment(
        forecast_id=forecast_assessment_id(
            ticker="AAPL", source_run_id="run-1", content_hash=content_hash
        ),
        ticker="AAPL",
        terms=terms,
        source_run_id="run-1",
        provider_invocation_id="prov-1",
        prompt_version="asset-analyst-full@test",
        artifact_version="h5-full@1",
        price_anchor=PriceAnchor(
            status=PriceAnchorStatus.OBSERVED,
            price=Decimal("100"),
            observed_at=TS,
        ),
        effective_at=TS,
        known_at=TS,
        content_hash=content_hash,
    )


def _snapshot(session: date, price: str) -> SessionPriceSnapshot:
    return SessionPriceSnapshot(
        session_date=session,
        price=Decimal(price),
        observed_at=CUTOFF,
        known_at=CUTOFF,
    )


def _build_outcome() -> ForecastOutcome:
    """Write-path outcome with un-quantized ``forecast_mean_return`` (0.0325)."""
    assessment = _assessment()
    return fo._build_resolved_outcome(
        base=assessment,
        effective_id=assessment.forecast_id,
        ticker="AAPL",
        horizon_sessions=21,
        reference_session=REF_SESSION,
        maturity_session=MAT_SESSION,
        reference_snapshot=_snapshot(REF_SESSION, "100"),
        maturity_snapshot=_snapshot(MAT_SESSION, "106"),
        forecast_mean_return=assessment.terms.scenario_mean_return(),
    )


def _postgrest_numeric_roundtrip(row: dict[str, object]) -> dict[str, object]:
    """Simulate PostgREST: ``numeric`` columns arrive as JSON numbers → float."""
    out = dict(row)
    for key in ("forecast_mean_return", "realized_return", "signed_residual"):
        if out.get(key) is not None:
            out[key] = float(str(out[key]))
    return out


def _stale_row() -> dict[str, object]:
    """A row hashed the pre-#4298 way: raw ``str(Decimal)``, trailing zeros kept."""
    outcome = _build_outcome()
    prefix_payload = {
        **outcome._hash_payload(),
        "forecast_mean_return": str(outcome.forecast_mean_return),
        "realized_return": str(outcome.realized_return),
        "signed_residual": str(outcome.signed_residual),
    }
    content_hash = forecast_outcome_content_hash(payload=prefix_payload)
    outcome_id = forecast_outcome_id(
        effective_forecast_id=outcome.effective_forecast_id,
        maturity_session=outcome.maturity_session,
        content_hash=content_hash,
    )
    row = fo._outcome_row(outcome)
    row["content_hash"] = content_hash
    row["outcome_id"] = str(outcome_id)
    return _postgrest_numeric_roundtrip(row)


def _ingress(row: dict[str, object]) -> list[ForecastOutcome]:
    client = FakeSupabaseClient(canned_reads={fo.OUTCOMES: [row]})
    return fo.list_resolved_outcomes_as_of(client=client, knowledge_cutoff_at=CUTOFF)


class TestNumericRoundTripIngress:
    def test_postgrest_numeric_roundtrip_resolves_without_skip_or_raise(self) -> None:
        outcome = _build_outcome()
        # Write-time spelling is fixed 8dp; the round trip loses trailing zeros.
        assert fo._outcome_row(outcome)["realized_return"] == "0.06000000"
        assert fo._outcome_row(outcome)["forecast_mean_return"] == "0.0325"
        stored = _postgrest_numeric_roundtrip(fo._outcome_row(outcome))
        assert stored["realized_return"] == 0.06
        assert stored["forecast_mean_return"] == 0.0325

        resolved = _ingress(stored)

        assert len(resolved) == 1
        assert resolved[0].outcome_id == outcome.outcome_id
        assert resolved[0].forecast_mean_return == MEAN
        assert resolved[0].realized_return == REALIZED
        assert resolved[0].signed_residual == RESIDUAL


class TestPrefixHashGuard:
    def test_prefix_raw_str_hash_fails_on_float_reload(self) -> None:
        """Guard: the pre-#4298 digest cannot survive the numeric round trip."""
        row = _stale_row()
        assert row["realized_return"] == 0.06
        payload = {k: row[k] for k in fo._OUTCOME_FIELDS if k in row}
        with pytest.raises(ValidationError, match="content_hash must match canonical"):
            ForecastOutcome.model_validate(payload)

    def test_daily_reader_fails_loud_instead_of_skipping(self) -> None:
        """The house reflect path must not silently drop a stale persisted row."""
        with pytest.raises(
            fo.ForecastOutcomeIntegrityError, match="repair_forecast_outcome_hashes"
        ):
            _ingress(_stale_row())


class TestHashRepairPlanner:
    def test_noop_on_canonical_row(self) -> None:
        row = _postgrest_numeric_roundtrip(fo._outcome_row(_build_outcome()))
        plan = fo.plan_forecast_outcome_hash_repairs(rows=[row])
        assert plan.repairs == ()
        assert plan.unrepairable == ()

    def test_repairs_stale_row_then_is_idempotent(self) -> None:
        stale = _stale_row()
        first = fo.plan_forecast_outcome_hash_repairs(rows=[stale])

        assert first.ok
        assert len(first.repairs) == 1
        repair = first.repairs[0]
        assert repair.outcome_id == stale["outcome_id"]
        assert repair.repaired_content_hash != repair.recorded_content_hash
        assert repair.repaired_outcome_id != repair.outcome_id

        repaired = {
            **stale,
            "outcome_id": repair.repaired_outcome_id,
            "content_hash": repair.repaired_content_hash,
        }
        # The rewritten row now validates, and a second pass is a no-op.
        ForecastOutcome.model_validate(
            {k: repaired[k] for k in fo._OUTCOME_FIELDS if k in repaired}
        )
        assert len(_ingress(repaired)) == 1
        second = fo.plan_forecast_outcome_hash_repairs(rows=[repaired])
        assert second.repairs == ()
        assert second.unrepairable == ()

    def test_genuinely_corrupt_row_is_unrepairable(self) -> None:
        row = _postgrest_numeric_roundtrip(fo._outcome_row(_build_outcome()))
        row["signed_residual"] = 0.5  # no longer realized_return - forecast_mean_return

        plan = fo.plan_forecast_outcome_hash_repairs(rows=[row])

        assert plan.repairs == ()
        assert len(plan.unrepairable) == 1
        assert not plan.ok
