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
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import psycopg.sql
import pytest
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
