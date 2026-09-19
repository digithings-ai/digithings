"""Repair-apply transaction path, calibration-lineage refusal, price-ingress hardening.

Closes epic #4295 wave-1 gaps G1–G3 for the forecast-outcome repair path:

* G1 — the ``--apply`` path had never been exercised. ``run_repair`` now accepts
  an injected connection factory, so a recording fake proves dry-run writes
  nothing, apply emits DISABLE → UPDATE → ENABLE in one transaction, a second
  pass is ``no_changes``, a mid-way failure rolls back (leaving the trigger
  enabled), and every statement is built with ``psycopg.sql``. This is a
  fake-connection proof, not a live-privileged-Postgres proof.
* G2 — a repair rewrites ``outcome_id``, which ``olympus_forecast_calibrations
  .outcome_ids`` cites. That array is covered by the calibration's immutable
  digest, so the planner refuses (and reports) rather than silently leaving
  stale lineage.
* G3 — ``_fetch_session_close`` must treat a non-finite or out-of-band raw close
  as an absent close (pending), not return NaN or an unrepresentable Decimal.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import psycopg.sql
import pytest
from digiquant.portfolio.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    ForecastCalibration,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
    forecast_calibration_content_hash,
    forecast_calibration_id,
)
from digiquant.research import forecast_outcomes as fo

from tests.dq.research.test_forecast_outcome_hash_ingress import (
    _build_outcome,
    _postgrest_numeric_roundtrip,
    _stale_row,
)

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
    / "repair_forecast_outcome_hashes.py"
)


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("repair_forecast_outcome_hashes_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()

TS = datetime(2026, 7, 15, 20, 0, tzinfo=UTC)


def _render(statement: Any) -> str | None:
    if isinstance(statement, str):
        return statement
    as_string = getattr(statement, "as_string", None)
    return as_string() if callable(as_string) else None


class _RecordingConnection:
    """Recording fake for the ``psycopg.connect(...)`` seam (no live Postgres).

    ``fetch_batches`` supplies successive SELECT result sets in execution order.
    ``fail_on`` raises on the Nth overall statement to exercise rollback.
    ``committed_trigger`` tracks the trigger state that would survive a commit,
    so a rollback that discards a pending DISABLE is observable.
    """

    def __init__(
        self,
        *,
        fetch_batches: list[list[dict[str, Any]]] | None = None,
        fail_on: int | None = None,
    ) -> None:
        self.fetch_batches = list(fetch_batches or [])
        self.fail_on = fail_on
        self.statements: list[tuple[Any, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self._rows: list[Any] = []
        self._pending_trigger: str | None = None
        self.committed_trigger = "enabled"

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self)

    def __enter__(self) -> _RecordingConnection:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            self.commits += 1
            if self._pending_trigger is not None:
                self.committed_trigger = self._pending_trigger
        else:
            self.rollbacks += 1
            self._pending_trigger = None
        return False

    def _execute(self, statement: Any, params: Any = None) -> None:
        self.statements.append((statement, params))
        if self.fail_on is not None and len(self.statements) == self.fail_on:
            raise RuntimeError("injected mid-transaction failure")
        rendered = _render(statement) or ""
        if "DISABLE TRIGGER" in rendered:
            self._pending_trigger = "disabled"
        elif "ENABLE TRIGGER" in rendered:
            self._pending_trigger = "enabled"
        if rendered.lstrip().upper().startswith("SELECT"):
            self._rows = self.fetch_batches.pop(0) if self.fetch_batches else []
        else:
            self._rows = []

    def kinds(self) -> list[str]:
        kinds: list[str] = []
        for statement, _params in self.statements:
            rendered = _render(statement) or ""
            if "DISABLE TRIGGER" in rendered:
                kinds.append("disable")
            elif "ENABLE TRIGGER" in rendered:
                kinds.append("enable")
            elif rendered.lstrip().upper().startswith("UPDATE"):
                kinds.append("update")
            elif rendered.lstrip().upper().startswith("SELECT"):
                kinds.append("select")
            else:
                kinds.append("other")
        return kinds


class _RecordingCursor:
    def __init__(self, conn: _RecordingConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def execute(self, statement: Any, params: Any = None) -> None:
        self._conn._execute(statement, params)

    def fetchall(self) -> list[Any]:
        return self._conn._rows


def _connect(conn: _RecordingConnection) -> Callable[[], _RecordingConnection]:
    return lambda: conn


def _run(conn: _RecordingConnection, *, apply: bool) -> dict[str, Any]:
    return script.run_repair(
        connect=_connect(conn),
        sql_module=psycopg.sql,
        apply=apply,
    )


# ─── G1: --apply transaction path ───────────────────────────────────────────


class TestApplyTransactionPathIsProven:
    def test_dry_run_performs_no_writes(self) -> None:
        stale = _stale_row()
        conn = _RecordingConnection(fetch_batches=[[stale], []])
        payload = _run(conn, apply=False)

        assert payload["status"] == "dry_run"
        assert len(payload["repairs"]) == 1
        assert conn.kinds() == ["select", "select"]
        assert "update" not in conn.kinds()
        assert "disable" not in conn.kinds()
        assert "enable" not in conn.kinds()
        assert conn.commits == 1
        assert conn.rollbacks == 0

    def test_apply_emits_disable_updates_enable_in_one_transaction(self) -> None:
        stale = _stale_row()
        conn = _RecordingConnection(fetch_batches=[[stale], []])
        payload = _run(conn, apply=True)

        assert payload["status"] == "applied"
        assert len(payload["repairs"]) == 1
        assert conn.kinds() == ["select", "select", "disable", "update", "enable"]
        # One connect() context, committed once, no rollback.
        assert conn.commits == 1
        assert conn.rollbacks == 0
        assert conn.committed_trigger == "enabled"

    def test_second_apply_over_repaired_rows_is_no_changes(self) -> None:
        canonical = _postgrest_numeric_roundtrip(fo._outcome_row(_build_outcome()))
        conn = _RecordingConnection(fetch_batches=[[canonical], []])
        payload = _run(conn, apply=True)

        assert payload["repairs"] == []
        assert payload["status"] == "no_changes"
        assert conn.kinds() == ["select", "select"]
        assert conn.commits == 1

    def test_mid_way_failure_rolls_back_and_does_not_leave_trigger_disabled(self) -> None:
        stale = _stale_row()
        # Statement 4 is the UPDATE, after DISABLE and before ENABLE.
        conn = _RecordingConnection(fetch_batches=[[stale], []], fail_on=4)
        with pytest.raises(RuntimeError, match="injected mid-transaction failure"):
            _run(conn, apply=True)

        assert conn.commits == 0
        assert conn.rollbacks == 1
        # DISABLE ran but was never committed, so the trigger stays enabled.
        assert conn.committed_trigger == "enabled"
        assert "enable" not in conn.kinds()

    def test_statements_are_identifier_safe_sql_objects(self) -> None:
        stale = _stale_row()
        conn = _RecordingConnection(fetch_batches=[[stale], []])
        _run(conn, apply=True)

        update = None
        for statement, params in conn.statements:
            assert isinstance(statement, psycopg.sql.Composable)
            assert not isinstance(statement, str)
            if (params or ()) and len(params) == 3:
                update = statement
        assert update is not None
        rendered = _render(update) or ""
        # Identifiers are quoted by psycopg.sql, never string-formatted.
        assert '"public"."forecast_outcomes"' in rendered
        assert "%s" in rendered
        # Values are bound parameters, not interpolated into the SQL text.
        assert stale["outcome_id"] not in rendered


# ─── G2: calibration lineage refusal ────────────────────────────────────────


class TestCalibrationLineageRefusal:
    def test_planner_repairs_uncited_stale_row(self) -> None:
        stale = _stale_row()
        plan = fo.plan_forecast_outcome_hash_repairs(rows=[stale])
        assert len(plan.repairs) == 1
        assert plan.unrepairable == ()

    def test_planner_refuses_row_cited_by_calibration(self) -> None:
        stale = _stale_row()
        plan = fo.plan_forecast_outcome_hash_repairs(
            rows=[stale],
            cited_outcome_ids={stale["outcome_id"]},
        )
        assert plan.repairs == ()
        assert len(plan.unrepairable) == 1
        assert "cited_by_calibration" in plan.unrepairable[0]
        assert not plan.ok

    def test_run_repair_reports_cited_row_and_emits_no_update(self) -> None:
        stale = _stale_row()
        conn = _RecordingConnection(
            fetch_batches=[[stale], [{"outcome_ids": [stale["outcome_id"]]}]],
        )
        payload = _run(conn, apply=True)

        assert payload["repairs"] == []
        assert payload["unrepairable"]
        assert "cited_by_calibration" in payload["unrepairable"][0]
        assert payload["status"] == "no_changes"
        assert "update" not in conn.kinds()
        assert "disable" not in conn.kinds()
        assert conn.rollbacks == 0


# ─── G3: price-ingress hardening ────────────────────────────────────────────


class TestPriceIngressHardening:
    @staticmethod
    def _r2_close(monkeypatch: pytest.MonkeyPatch, close: Any) -> None:
        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            return [{"ticker": "AAPL", "date": "2026-08-13", "close": close}]

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)

    def test_nan_close_is_absent_not_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Guard: the pre-fix path returned a NaN Decimal; NaN <= 0 is False.
        assert not Decimal("nan").quantize(fo._PRICE_QUANTUM).is_finite()
        self._r2_close(monkeypatch, "nan")
        assert (
            fo._fetch_session_close(client=None, ticker="AAPL", session=date(2026, 8, 13)) is None
        )

    def test_absurd_above_band_close_is_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Guard: pre-fix returned this, which PositivePrice (max_digits=20) rejects.
        huge = Decimal(str(1e19))
        assert huge.quantize(fo._PRICE_QUANTUM) >= fo._PRICE_MAX_EXCLUSIVE
        self._r2_close(monkeypatch, 1e19)
        assert (
            fo._fetch_session_close(client=None, ticker="AAPL", session=date(2026, 8, 13)) is None
        )

    def test_valid_float_close_still_quantizes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._r2_close(monkeypatch, 10.380000114440918)
        price = fo._fetch_session_close(client=None, ticker="AAPL", session=date(2026, 8, 13))
        assert price == Decimal("10.38000011")

    def test_max_representable_close_is_still_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Control: the band guard must not reject a legitimately large price.
        self._r2_close(monkeypatch, "999999999999.99999999")
        price = fo._fetch_session_close(client=None, ticker="AAPL", session=date(2026, 8, 13))
        assert price == Decimal("999999999999.99999999")
        fo.SessionPriceSnapshot(
            session_date=date(2026, 8, 13),
            price=price,
            observed_at=TS,
            known_at=TS,
        )


# ─── G2 cascade: rewrite the rows that cite a repaired outcome ──────────────


_CASCADE_TS = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
_BASE_ID = UUID("11111111-1111-4111-8111-111111111111")
_EFF_ID = UUID("22222222-2222-4222-8222-222222222222")
_COHORT_KEY = "horizon:21|regime:default"
_METHOD_VERSION = "shadow-calibrator@1"


def _citing_calibration(outcome_id: UUID | str) -> ForecastCalibration:
    """A canonically hashed AVAILABLE calibration citing ``outcome_id``."""
    fields: dict[str, Any] = {
        "cohort_key": _COHORT_KEY,
        "prior_definition": "zero_mean_shrinkage@v1",
        "method_version": _METHOD_VERSION,
        "sample_count": 1,
        "equivalent_sample_size": Decimal("0.50000000"),
        "bias": Decimal("0.02000000"),
        "dispersion": Decimal("0.08000000"),
        "brier_score": Decimal("0.18000000"),
        "log_score": Decimal("-0.45000000"),
        "reliability": Decimal("0.25000000"),
        "status": CalibrationArtifactStatus.AVAILABLE,
        "unavailable_reason": None,
        "outcome_ids": (UUID(str(outcome_id)),),
        "effective_at": _CASCADE_TS,
        "known_at": _CASCADE_TS,
    }
    content_hash = forecast_calibration_content_hash(
        payload=ForecastCalibration.model_construct(**fields)._hash_payload()
    )
    return ForecastCalibration(
        **fields,
        content_hash=content_hash,
        calibration_id=forecast_calibration_id(
            cohort_key=_COHORT_KEY,
            method_version=_METHOD_VERSION,
            content_hash=content_hash,
        ),
    )


def _anchored_calibrated(calibration: ForecastCalibration) -> CalibratedForecast:
    """A canonically hashed AVAILABLE calibrated forecast anchored to ``calibration``."""
    fields: dict[str, Any] = {
        "base_forecast_id": _BASE_ID,
        "effective_forecast_id": _EFF_ID,
        "calibration_id": calibration.calibration_id,
        "ticker": "AAPL",
        "expected_gross_return": Decimal("0.03000000"),
        "forecast_error_std": Decimal("0.09000000"),
        "downside_quantiles": (Decimal("-0.20000000"), Decimal("-0.10000000")),
        "calibrated_positive_probability": Decimal("0.55000000"),
        "reliability_weight": Decimal("0.25000000"),
        "effective_until": _CASCADE_TS + timedelta(days=21),
        "status": CalibrationArtifactStatus.AVAILABLE,
        "unavailable_reason": None,
        "effective_at": _CASCADE_TS,
        "known_at": _CASCADE_TS,
    }
    content_hash = calibrated_forecast_content_hash(
        payload=CalibratedForecast.model_construct(**fields)._hash_payload()
    )
    return CalibratedForecast(
        **fields,
        content_hash=content_hash,
        calibrated_forecast_id=calibrated_forecast_id(
            effective_forecast_id=_EFF_ID,
            calibration_id=calibration.calibration_id,
            content_hash=content_hash,
        ),
    )


def _calibration_row(calibration: ForecastCalibration) -> dict[str, Any]:
    return calibration.model_dump(mode="json")


def _calibrated_row(subject: CalibratedForecast) -> dict[str, Any]:
    return subject.model_dump(mode="json")


def _cascade_fixtures() -> tuple[dict[str, Any], ForecastCalibration, CalibratedForecast]:
    stale = _stale_row()
    calibration = _citing_calibration(stale["outcome_id"])
    return stale, calibration, _anchored_calibrated(calibration)


def _run_cascade(conn: _RecordingConnection, *, apply: bool) -> dict[str, Any]:
    return script.run_cascade_repair(
        connect=_connect(conn),
        sql_module=psycopg.sql,
        apply=apply,
    )


def _rendered_statements(conn: _RecordingConnection) -> list[str]:
    return [_render(statement) or "" for statement, _params in conn.statements]


class TestCascadeTransactionPath:
    def test_dry_run_plans_the_whole_chain_and_writes_nothing(self) -> None:
        stale, calibration, subject = _cascade_fixtures()
        conn = _RecordingConnection(
            fetch_batches=[[stale], [_calibration_row(calibration)], [_calibrated_row(subject)]]
        )
        payload = _run_cascade(conn, apply=False)

        assert payload["status"] == "dry_run"
        assert payload["mode"] == "cascade"
        assert len(payload["outcomes"]) == 1
        assert len(payload["calibrations"]) == 1
        assert len(payload["calibrated_forecasts"]) == 1
        assert payload["unrepairable"] == []
        # One README select per table, nothing else.
        assert conn.kinds() == ["select", "select", "select"]
        assert conn.commits == 1
        assert conn.rollbacks == 0

    def test_apply_disables_three_triggers_then_writes_then_reenables(self) -> None:
        stale, calibration, subject = _cascade_fixtures()
        conn = _RecordingConnection(
            fetch_batches=[[stale], [_calibration_row(calibration)], [_calibrated_row(subject)]]
        )
        payload = _run_cascade(conn, apply=True)

        assert payload["status"] == "applied"
        # 3 selects, 3 DISABLEs, then detach + outcome + calibration + calibrated
        # UPDATEs, then 3 ENABLEs — all in one transaction.
        assert conn.kinds() == ["select"] * 3 + ["disable"] * 3 + ["update"] * 4 + ["enable"] * 3
        assert conn.commits == 1
        assert conn.rollbacks == 0
        assert conn.committed_trigger == "enabled"

    def test_citation_is_detached_before_it_is_rewritten(self) -> None:
        stale, calibration, subject = _cascade_fixtures()
        conn = _RecordingConnection(
            fetch_batches=[[stale], [_calibration_row(calibration)], [_calibrated_row(subject)]]
        )
        _run_cascade(conn, apply=True)

        rendered = _rendered_statements(conn)
        detach = next(i for i, sql in enumerate(rendered) if "SET calibration_id = NULL" in sql)
        outcome_update = next(
            i
            for i, sql in enumerate(rendered)
            if sql.lstrip().upper().startswith("UPDATE") and "forecast_outcomes" in sql
        )
        calibration_update = next(i for i, sql in enumerate(rendered) if "outcome_ids = %s" in sql)
        # FK-safe order: clear the referencing FK, rewrite the outcome id, and
        # only then rewrite the cited calibration id.
        assert detach < calibration_update
        assert outcome_update < calibration_update

    def test_refused_plan_writes_nothing(self) -> None:
        stale, calibration, _subject = _cascade_fixtures()
        broken = {**_calibration_row(calibration), "status": "not-a-status"}
        conn = _RecordingConnection(fetch_batches=[[stale], [broken], []])
        payload = _run_cascade(conn, apply=True)

        assert payload["unrepairable"]
        assert conn.kinds() == ["select", "select", "select"]
        assert conn.rollbacks == 0
        # Nothing was written, so the reported status is a dry run.
        assert payload["status"] == "dry_run"

    def test_second_cascade_apply_is_no_changes(self) -> None:
        stale = _stale_row()
        planned = fo.plan_forecast_outcome_cascade_repairs(
            outcome_rows=[stale], calibration_rows=[], calibrated_forecast_rows=[]
        )
        repair = planned.outcomes[0]
        canonical = {
            **stale,
            "outcome_id": repair.repaired_outcome_id,
            "content_hash": repair.repaired_content_hash,
        }
        calibration = _citing_calibration(repair.repaired_outcome_id)
        subject = _anchored_calibrated(calibration)
        conn = _RecordingConnection(
            fetch_batches=[[canonical], [_calibration_row(calibration)], [_calibrated_row(subject)]]
        )
        payload = _run_cascade(conn, apply=True)

        assert payload["status"] == "no_changes"
        assert payload["outcomes"] == []
        assert payload["calibrations"] == []
        assert payload["calibrated_forecasts"] == []
        assert conn.kinds() == ["select", "select", "select"]
        assert conn.commits == 1

    def test_citation_array_is_bound_as_a_list_not_a_tuple(self) -> None:
        stale, calibration, subject = _cascade_fixtures()
        conn = _RecordingConnection(
            fetch_batches=[[stale], [_calibration_row(calibration)], [_calibrated_row(subject)]]
        )
        _run_cascade(conn, apply=True)

        bound: Any = None
        for statement, params in conn.statements:
            if params and len(params) == 4 and "outcome_ids" in (_render(statement) or ""):
                bound = params[2]
        # A tuple adapts as a composite record ('(a,b)'), which Postgres rejects
        # as a malformed array literal — the citation must bind as a list.
        assert isinstance(bound, list)
        assert all(isinstance(item, UUID) for item in bound)
        assert len(bound) == 1

    def test_mid_way_failure_rolls_back_and_leaves_all_triggers_enabled(self) -> None:
        stale, calibration, subject = _cascade_fixtures()
        # Statement 9 is the citation UPDATE: after all three DISABLEs, before any ENABLE.
        conn = _RecordingConnection(
            fetch_batches=[[stale], [_calibration_row(calibration)], [_calibrated_row(subject)]],
            fail_on=9,
        )
        with pytest.raises(RuntimeError, match="injected mid-transaction failure"):
            _run_cascade(conn, apply=True)

        assert conn.commits == 0
        assert conn.rollbacks == 1
        assert conn.committed_trigger == "enabled"
        assert "enable" not in conn.kinds()

    def test_uncited_stale_outcome_plans_no_cascade_rows(self) -> None:
        stale = _stale_row()
        conn = _RecordingConnection(fetch_batches=[[stale], [], []])
        payload = _run_cascade(conn, apply=True)

        assert len(payload["outcomes"]) == 1
        assert payload["calibrations"] == []
        assert payload["calibrated_forecasts"] == []
        # Only the outcome table needs its trigger touched here.
        assert conn.kinds().count("disable") == 3
