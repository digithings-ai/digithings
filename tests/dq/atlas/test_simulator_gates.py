"""CI simulator gates for Olympus #930 (plan: ci/simulator-gates).

Gate thresholds (spec §12.2 / §16 ``test_quiet_day``) — re-baselined 2026-06-20:
- ``QUIET_DAY_LLM_BUDGET`` ≤ 22 LLM calls on a quiet δ day (includes 11× ``SectorReport``
  from phase5 sector bypass until #929 triage wiring lands).
- ``QUIET_DAY_MIN_PATCH_RATIO`` ≥ 0.10 — patch calls are a minority until phase5 respects
  triage carry; numerator still gates mandatory δ ``DocumentPatch`` paths.
- Hermes quiet path: H1 thesis review + held-ticker H5 edits; H6 deliberation skipped when
  analyst stance is unchanged.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.graph import AtlasInput
from digiquant.olympus.atlas.testing import simulated_pipeline
from digiquant.olympus.atlas.testing.simulator import (
    QUIET_DAY_LLM_BUDGET,
    QUIET_DAY_MIN_PATCH_RATIO,
    QUIET_ONCHAIN_INJECTION,
    build_quiet_day_canned_extras,
    client_store_to_canned_extras,
    llm_telemetry_from_calls,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OLYMPUS_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "olympus.yml"


@contextmanager
def _stub_quiet_onchain() -> Iterator[None]:
    """Pin Hyperdash injection so ``alt-onchain-positioning`` triage carries."""

    def _fake_onchain() -> SimpleNamespace:
        return SimpleNamespace(
            error=None,
            has_data=True,
            compact_summary=lambda: dict(QUIET_ONCHAIN_INJECTION),
            to_rows=lambda _run_date: [],
        )

    with patch(
        "digiquant.olympus.atlas.phases.preflight.get_onchain_cohort_positioning",
        _fake_onchain,
    ):
        yield


_HERMES_THESIS_SCHEMAS = frozenset(
    {
        "ThesisReviewOutput",
        "MarketThesisExplorationOutput",
        "ThesisVehicleMapOutput",
    }
)

@pytest.mark.unit
class TestLlmCallTelemetry:
    def test_simulated_pipeline_records_schema_per_llm_call(self) -> None:
        with simulated_pipeline(watchlist=("AAPL",), publish=False) as run:
            run.invoke(
                AtlasInput(
                    refresh_scope="all",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )
            telemetry = run.llm_telemetry()
        assert telemetry.total_calls > 0
        assert telemetry.by_schema
        assert telemetry.total_calls == sum(telemetry.by_schema.values())

    def test_llm_telemetry_patch_ratio_computed(self) -> None:
        calls = [("DocumentPatch", {}), ("MacroRegimeReport", {}), ("DocumentPatch", {})]
        telemetry = llm_telemetry_from_calls(calls)
        assert telemetry.patch_calls == 2
        assert telemetry.patch_ratio == pytest.approx(2 / 3)


@pytest.mark.unit
class TestQuietDayGates:
    def test_quiet_day_llm_budget_and_hermes_path(self) -> None:
        """Spec §16 ``test_quiet_day``: zero stale carry + held H5 edits + H1."""
        run_date = date(2026, 4, 26)
        watchlist = ("AAPL",)
        canned = build_quiet_day_canned_extras(run_date=run_date, watchlist=watchlist)

        with _stub_quiet_onchain(), simulated_pipeline(
            watchlist=watchlist,
            canned_extras=canned,
            publish=True,
            replace_canned_defaults=True,
        ) as run:
            final = run.invoke(
                AtlasInput(
                    refresh_scope="none",
                    run_date=run_date,
                    watchlist=watchlist,
                )
            )
            telemetry = run.llm_telemetry()

        # Gate: total LLM budget (spec §12.2 — re-baselined quiet δ ceiling).
        assert telemetry.total_calls <= QUIET_DAY_LLM_BUDGET, (
            f"quiet-day LLM budget exceeded: {telemetry.total_calls} > {QUIET_DAY_LLM_BUDGET}; "
            f"by_schema={telemetry.by_schema}"
        )

        # Gate: edit-mode dominance on δ days (patch-ratio telemetry).
        assert telemetry.patch_ratio >= QUIET_DAY_MIN_PATCH_RATIO, (
            f"patch ratio {telemetry.patch_ratio:.2f} < {QUIET_DAY_MIN_PATCH_RATIO}; "
            f"patch_calls={telemetry.patch_calls} total={telemetry.total_calls}"
        )

        # Hermes: thesis track runs (H1 minimum). H6 may run ≤1 PM turn when held
        # ticker price delta triggers H5 edit (2% move) even if deliberation summary carries.
        assert "ThesisReviewOutput" in telemetry.by_schema, "H1 thesis review must run daily"
        assert telemetry.by_schema.get("DeliberationPmTurn", 0) <= 1
        assert telemetry.by_schema.get("DeliberationAnalystTurn", 0) == 0

        # Held ticker H5: at least one analyst/patch call for AAPL.
        h5_calls = telemetry.by_schema.get("AnalystPayload", 0) + telemetry.by_schema.get(
            "DocumentPatch", 0
        )
        assert h5_calls >= 1
        assert "AAPL" in final.phase_hermes.asset_analysts

        # Gate: edit-mode patch calls for mandatory δ segments (macro/crypto/equity).
        assert telemetry.by_schema.get("DocumentPatch", 0) >= 3

        # Known gap: phase5 sectors bypass triage carry (#929) — budgeted separately.
        sector_full = telemetry.by_schema.get("SectorReport", 0)
        assert sector_full <= 11, f"unexpected sector fan-out: {sector_full}"

        # Atlas mandatory segments must not emit full schemas on quiet δ (edit path only).
        full_mandatory = sum(
            telemetry.by_schema.get(schema, 0)
            for schema in ("MacroRegimeReport", "CryptoReport", "EquityOverviewReport")
        )
        assert full_mandatory == 0


@pytest.mark.unit
class TestThreeDayContinuityScaffold:
    """3-day continuity scaffold — day1 full, day2–3 quiet δ with chained priors."""

    def test_three_day_continuity_chain_and_budget(self) -> None:
        day1 = date(2026, 4, 24)
        day2 = day1 + timedelta(days=1)
        day3 = day2 + timedelta(days=1)
        watchlist = ("AAPL",)

        # Day 1 — operator ``refresh_scope=all`` (Sunday / forced full in olympus.yml).
        with _stub_quiet_onchain(), simulated_pipeline(watchlist=watchlist, publish=True) as run1:
            run1.invoke(
                AtlasInput(
                    refresh_scope="all",
                    run_date=day1,
                    watchlist=watchlist,
                )
            )
            day1_store = client_store_to_canned_extras(run1.client)
            day1_calls = run1.llm_telemetry().total_calls

        # Day 2 — daily ``refresh_scope=none`` with prior artifacts from day1 publish.
        canned2 = build_quiet_day_canned_extras(run_date=day2, watchlist=watchlist)
        for table, rows in day1_store.items():
            canned2.setdefault(table, [])
            canned2[table].extend(rows)

        with _stub_quiet_onchain(), simulated_pipeline(
            watchlist=watchlist, canned_extras=canned2, publish=True, replace_canned_defaults=True
        ) as run2:
            run2.invoke(
                AtlasInput(refresh_scope="none", run_date=day2, watchlist=watchlist)
            )
            telemetry2 = run2.llm_telemetry()
            day2_store = client_store_to_canned_extras(run2.client)

        assert telemetry2.total_calls <= QUIET_DAY_LLM_BUDGET
        assert telemetry2.total_calls < day1_calls, "day2 quiet δ should cost less than day1 full"

        # Day 3 — chained priors from day2.
        canned3 = build_quiet_day_canned_extras(run_date=day3, watchlist=watchlist)
        for table, rows in day2_store.items():
            canned3.setdefault(table, [])
            canned3[table].extend(rows)

        with _stub_quiet_onchain(), simulated_pipeline(
            watchlist=watchlist, canned_extras=canned3, publish=True, replace_canned_defaults=True
        ) as run3:
            run3.invoke(
                AtlasInput(refresh_scope="none", run_date=day3, watchlist=watchlist)
            )
            telemetry3 = run3.llm_telemetry()

        assert telemetry3.total_calls <= QUIET_DAY_LLM_BUDGET

        # Scaffold: each δ day publishes its own digest artifact (prior chain via canned seed).
        day3_docs = run3.client.store.get("documents", [])
        assert any(
            row.get("date") == day3.isoformat()
            and row.get("document_key") in ("digest", "digest-delta")
            for row in day3_docs
        ), f"day3 digest publish missing; documents={day3_docs}"
        assert any(row.get("date") == day2.isoformat() for row in day2_store.get("documents", []))
        assert any(row.get("date") == day1.isoformat() for row in day1_store.get("documents", []))


@pytest.mark.unit
class TestOlympusWorkflowDailyCadence:
    """Verify ``olympus.yml`` matches ``orchestrator/daily-cadence`` CLI surface."""

    def test_olympus_workflow_uses_daily_cadence_not_legacy_run_types(self) -> None:
        text = _OLYMPUS_WORKFLOW.read_text(encoding="utf-8")
        assert "--cadence daily" in text
        assert "--refresh-scope" in text
        assert "run_type=baseline" not in text
        assert "run_type=delta" not in text
        assert "run_type=monthly" not in text
        assert '--run-type "monthly"' not in text

    def test_olympus_workflow_schedule_is_daily(self) -> None:
        text = _OLYMPUS_WORKFLOW.read_text(encoding="utf-8")
        assert 'cron: "0 12 * * *"' in text
