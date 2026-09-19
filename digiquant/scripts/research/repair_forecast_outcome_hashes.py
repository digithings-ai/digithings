#!/usr/bin/env python3
"""Repair stored ForecastOutcome content_hash / outcome_id digests (#4298).

Why this exists
---------------
``forecast_outcomes`` persists return fractions in Postgres ``numeric``
columns. ``numeric`` does not preserve trailing zeros, so a row written before
#4298 with the raw ``str(Decimal)`` spelling (e.g. ``0.0325``) recomputes to a
different canonical digest now that hashing is fixed at 8dp. The daily reader
fails loud on such a row, so this one-shot rewrites the two hash-bearing columns.

Append-only table
-----------------
The table is append-only (migration 080): ``reject_forecast_outcomes_mutation``
rejects UPDATE/DELETE/TRUNCATE for every role, and ``service_role`` holds
SELECT+INSERT only. The repair therefore needs a **privileged direct Postgres
URI** (``CORE_POSTGRES_URI`` or ``DATABASE_URL``) whose role owns the table —
not the PostgREST service key. The UPDATEs run in one transaction with the
mutation trigger disabled and re-enabled around them; any failure rolls the whole
transaction back, which restores the trigger on its own.

``outcome_id`` PK churn
-----------------------
Repairing the digest changes ``outcome_id`` (its UUID5 input). The
``forecast_calibrations.outcome_ids`` array cites those UUIDs and is not
a foreign key, so it would go stale. Two modes:

* default — **refuse** any row still cited by a calibration, reporting it under
  ``unrepairable`` with the reason; never rewrites a row and silently leaves
  stale lineage (#4295 G2).
* ``--cascade`` — rewrite the whole bounded citation chain in the same
  transaction: the outcome's ``outcome_id``/``content_hash``, then each citing
  ``forecast_calibrations`` row's ``outcome_ids``/``content_hash``/
  ``calibration_id``, then each anchored ``calibrated_forecasts`` row's
  ``calibration_id``/``content_hash``/``calibrated_forecast_id``. Nothing has a
  foreign key pointing at ``forecast_outcomes``, so the chain ends there.
  A plan containing anything ``unrepairable`` writes nothing at all.

Default mode is a dry run; pass ``--apply`` to write.

Usage::

    PYTHONPATH=digiquant/src:. python digiquant/scripts/research/repair_forecast_outcome_hashes.py
    PYTHONPATH=digiquant/src:. python digiquant/scripts/research/repair_forecast_outcome_hashes.py --apply
    PYTHONPATH=digiquant/src:. python digiquant/scripts/research/repair_forecast_outcome_hashes.py --cascade --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _path in (str(_REPO_ROOT / "digiquant" / "src"), str(_SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from _env import load_repo_env  # noqa: E402

from digiquant.research.forecast_outcomes import (  # noqa: E402
    OUTCOMES,
    ForecastOutcomeCascadePlan,
    ForecastOutcomeHashRepairPlan,
    _calibration_source_fields,
    plan_forecast_outcome_cascade_repairs,
    plan_forecast_outcome_hash_repairs,
)
from digiquant.research.forecast_registry import (  # noqa: E402
    CALIBRATED_FORECASTS,
    CALIBRATIONS,
)

logger = logging.getLogger(__name__)

# Canonical (post-#4295) object names. Every trigger is derived from its table
# constant so it tracks the same rename (``reject_<table>_mutation``); the citing
# tables come from the registry constants, not literals.
_TRIGGER = f"reject_{OUTCOMES}_mutation"
_CALIBRATIONS = CALIBRATIONS
_CALIBRATION_TRIGGER = f"reject_{CALIBRATIONS}_mutation"
_CALIBRATED_FORECASTS = CALIBRATED_FORECASTS
_CALIBRATED_FORECAST_TRIGGER = f"reject_{CALIBRATED_FORECASTS}_mutation"
_URI_ENV_VARS = ("CORE_POSTGRES_URI", "DATABASE_URL")


def _import_psycopg() -> tuple[Any, Any, Any]:
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - optional in minimal installs
        raise SystemExit(
            "psycopg is required for the direct Postgres repair (pip install 'digiquant[research]')"
        ) from exc
    return psycopg, sql, dict_row


def _resolve_uri(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    for name in _URI_ENV_VARS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    raise SystemExit(
        "set --postgres-uri or " + "/".join(_URI_ENV_VARS) + " (privileged direct Postgres URI)"
    )


def _status_label(*, apply: bool, repairs: int) -> str:
    """Accurate run outcome: ``--apply`` with nothing to do is NOT a dry run."""
    if not apply:
        return "dry_run"
    return "applied" if repairs else "no_changes"


def _payload(
    *,
    rows_scanned: int,
    plan: ForecastOutcomeHashRepairPlan,
    apply: bool,
) -> dict[str, Any]:
    return {
        "table": OUTCOMES,
        "rows_scanned": rows_scanned,
        "repairs": [
            {
                "outcome_id": repair.outcome_id,
                "repaired_outcome_id": repair.repaired_outcome_id,
                "recorded_content_hash": repair.recorded_content_hash,
                "repaired_content_hash": repair.repaired_content_hash,
            }
            for repair in plan.repairs
        ],
        "unrepairable": list(plan.unrepairable),
        "apply": apply,
        "status": _status_label(apply=apply, repairs=len(plan.repairs)),
    }


def run_repair(
    *,
    connect: Callable[[], Any],
    sql_module: Any,
    apply: bool,
    limit: int | None = None,
) -> dict[str, Any]:
    """Drive one repair pass against an injected connection factory.

    ``connect`` returns a psycopg-style connection used as a context manager:
    clean exit commits, an exception rolls back. Production passes
    ``functools.partial(psycopg.connect, uri, row_factory=dict_row)``; tests pass
    a recording fake so the transaction path is provable without a live
    privileged Postgres (#4295 G1). All statements are built with
    ``sql_module`` (``psycopg.sql``), so table/trigger identifiers are never
    string-formatted and values stay bound parameters.

    The citation read, the plan, and the DISABLE/UPDATE/ENABLE writes all run in
    the one ``connect()`` transaction, so a mid-way failure rolls the whole pass
    back and the trigger is restored on its own.
    """
    table = sql_module.Identifier("public", OUTCOMES)
    calibrations = sql_module.Identifier("public", _CALIBRATIONS)
    select_sql = sql_module.SQL("SELECT * FROM {} ORDER BY known_at").format(table)
    cited_sql = sql_module.SQL("SELECT outcome_ids FROM {}").format(calibrations)
    update_sql = sql_module.SQL(
        "UPDATE {} SET outcome_id = %s, content_hash = %s WHERE outcome_id = %s"
    ).format(table)
    disable_sql = sql_module.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
        table, sql_module.Identifier(_TRIGGER)
    )
    enable_sql = sql_module.SQL("ALTER TABLE {} ENABLE TRIGGER {}").format(
        table, sql_module.Identifier(_TRIGGER)
    )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(select_sql)
            rows = [dict(row) for row in cur.fetchall()]
            cur.execute(cited_sql)
            cited: set[str] = set()
            for cited_row in cur.fetchall():
                for item in dict(cited_row).get("outcome_ids") or ():
                    cited.add(str(item))
        if limit is not None:
            rows = rows[:limit]

        plan = plan_forecast_outcome_hash_repairs(rows=rows, cited_outcome_ids=cited)

        if apply and plan.repairs:
            with conn.cursor() as cur:
                cur.execute(disable_sql)
                for repair in plan.repairs:
                    cur.execute(
                        update_sql,
                        (
                            repair.repaired_outcome_id,
                            repair.repaired_content_hash,
                            repair.outcome_id,
                        ),
                    )
                cur.execute(enable_sql)

    return _payload(rows_scanned=len(rows), plan=plan, apply=apply)


def _cascade_payload(
    *,
    outcomes_scanned: int,
    plan: ForecastOutcomeCascadePlan,
    apply: bool,
) -> dict[str, Any]:
    return {
        "table": OUTCOMES,
        "mode": "cascade",
        "rows_scanned": outcomes_scanned,
        "outcomes": [
            {
                "outcome_id": repair.outcome_id,
                "repaired_outcome_id": repair.repaired_outcome_id,
                "recorded_content_hash": repair.recorded_content_hash,
                "repaired_content_hash": repair.repaired_content_hash,
            }
            for repair in plan.outcomes
        ],
        "calibrations": [
            {
                "calibration_id": repair.calibration_id,
                "repaired_calibration_id": repair.repaired_calibration_id,
                "recorded_content_hash": repair.recorded_content_hash,
                "repaired_content_hash": repair.repaired_content_hash,
            }
            for repair in plan.calibrations
        ],
        "calibrated_forecasts": [
            {
                "calibrated_forecast_id": repair.calibrated_forecast_id,
                "repaired_calibrated_forecast_id": repair.repaired_calibrated_forecast_id,
                "recorded_content_hash": repair.recorded_content_hash,
                "repaired_content_hash": repair.repaired_content_hash,
            }
            for repair in plan.calibrated_forecasts
        ],
        "unrepairable": list(plan.unrepairable),
        "apply": apply,
        # A refused plan writes nothing, so it reports a dry-run status even when
        # ``--apply`` was requested; ``unrepairable`` carries the refusal reasons.
        "status": _status_label(apply=apply and plan.ok, repairs=plan.writes),
    }


def run_cascade_repair(
    *,
    connect: Callable[[], Any],
    sql_module: Any,
    apply: bool,
    limit: int | None = None,
) -> dict[str, Any]:
    """Repair stale outcome digests AND the citation churn they force (#4295 G2).

    Extends :func:`run_repair` with the bounded three-table cascade: rewriting an
    ``outcome_id`` that a calibration still cites would leave
    ``forecast_calibrations.outcome_ids`` (and, transitively,
    ``calibrated_forecasts.calibration_id``) stale, so those rows are rewritten
    alongside it. Everything runs in one ``connect()`` transaction with all three
    append-only mutation triggers disabled and re-enabled around the writes; any
    failure — including a plan with anything under ``unrepairable`` — writes
    nothing and rolls back, so no partial cascade is ever committed.

    ``limit`` bounds the number of outcome rows inspected, matching
    :func:`run_repair`; the citing tables are read in full so the cascade is
    always complete for the outcomes it plans.
    """
    table = sql_module.Identifier("public", OUTCOMES)
    calibrations = sql_module.Identifier("public", _CALIBRATIONS)
    calibrated = sql_module.Identifier("public", _CALIBRATED_FORECASTS)

    select_outcomes = sql_module.SQL("SELECT * FROM {} ORDER BY known_at").format(table)
    select_calibrations = sql_module.SQL("SELECT * FROM {} ORDER BY known_at").format(calibrations)
    select_calibrated = sql_module.SQL("SELECT * FROM {} ORDER BY known_at").format(calibrated)

    update_outcome = sql_module.SQL(
        "UPDATE {} SET outcome_id = %s, content_hash = %s WHERE outcome_id = %s"
    ).format(table)
    update_calibration = sql_module.SQL(
        "UPDATE {} SET calibration_id = %s, content_hash = %s, outcome_ids = %s "
        "WHERE calibration_id = %s"
    ).format(calibrations)
    clear_calibrated = sql_module.SQL(
        "UPDATE {} SET calibration_id = NULL WHERE calibrated_forecast_id = %s"
    ).format(calibrated)
    update_calibrated = sql_module.SQL(
        "UPDATE {} SET calibrated_forecast_id = %s, calibration_id = %s, content_hash = %s "
        "WHERE calibrated_forecast_id = %s"
    ).format(calibrated)

    disable_outcomes = sql_module.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
        table, sql_module.Identifier(_TRIGGER)
    )
    enable_outcomes = sql_module.SQL("ALTER TABLE {} ENABLE TRIGGER {}").format(
        table, sql_module.Identifier(_TRIGGER)
    )
    disable_calibrations = sql_module.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
        calibrations, sql_module.Identifier(_CALIBRATION_TRIGGER)
    )
    enable_calibrations = sql_module.SQL("ALTER TABLE {} ENABLE TRIGGER {}").format(
        calibrations, sql_module.Identifier(_CALIBRATION_TRIGGER)
    )
    disable_calibrated = sql_module.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
        calibrated, sql_module.Identifier(_CALIBRATED_FORECAST_TRIGGER)
    )
    enable_calibrated = sql_module.SQL("ALTER TABLE {} ENABLE TRIGGER {}").format(
        calibrated, sql_module.Identifier(_CALIBRATED_FORECAST_TRIGGER)
    )

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(select_outcomes)
            outcome_rows = [dict(row) for row in cur.fetchall()]
            cur.execute(select_calibrations)
            calibration_rows = [dict(row) for row in cur.fetchall()]
            cur.execute(select_calibrated)
            calibrated_rows = [dict(row) for row in cur.fetchall()]
        if limit is not None:
            outcome_rows = outcome_rows[:limit]

        plan = plan_forecast_outcome_cascade_repairs(
            outcome_rows=outcome_rows,
            calibration_rows=calibration_rows,
            calibrated_forecast_rows=calibrated_rows,
        )

        # A partial cascade is never written: any unrepairable row aborts the pass.
        if apply and plan.writes and plan.ok:
            calibration_by_id = {repair.calibration_id: repair for repair in plan.calibrations}
            outcome_id_map = {item.outcome_id: item.repaired_outcome_id for item in plan.outcomes}
            # ``uuid[]`` must reach psycopg as a list: a tuple adapts as a composite
            # record ('(a,b)'), which Postgres rejects as a malformed array literal.
            new_outcome_ids: dict[str, list[UUID]] = {}
            for row in calibration_rows:
                fields = _calibration_source_fields(row)
                calibration_id = str(fields.get("calibration_id") or "")
                repair = calibration_by_id.get(calibration_id)
                if repair is None:
                    continue
                new_outcome_ids[calibration_id] = [
                    UUID(outcome_id_map.get(str(item), str(item)))
                    for item in fields.get("outcome_ids") or ()
                ]
            new_calibration_by_cf: dict[str, str] = {}
            for row in calibrated_rows:
                calibrated_forecast_id = str(row.get("calibrated_forecast_id"))
                calibration_id = row.get("calibration_id")
                if calibration_id is None:
                    continue
                repair = calibration_by_id.get(str(calibration_id))
                if repair is not None:
                    new_calibration_by_cf[calibrated_forecast_id] = repair.repaired_calibration_id
            with conn.cursor() as cur:
                cur.execute(disable_outcomes)
                cur.execute(disable_calibrations)
                cur.execute(disable_calibrated)
                # FK-safe: detach the citing rows before their calibration id moves.
                for repair in plan.calibrated_forecasts:
                    cur.execute(clear_calibrated, (repair.calibrated_forecast_id,))
                for repair in plan.outcomes:
                    cur.execute(
                        update_outcome,
                        (
                            repair.repaired_outcome_id,
                            repair.repaired_content_hash,
                            repair.outcome_id,
                        ),
                    )
                for repair in plan.calibrations:
                    cur.execute(
                        update_calibration,
                        (
                            repair.repaired_calibration_id,
                            repair.repaired_content_hash,
                            new_outcome_ids.get(repair.calibration_id, []),
                            repair.calibration_id,
                        ),
                    )
                for repair in plan.calibrated_forecasts:
                    cur.execute(
                        update_calibrated,
                        (
                            repair.repaired_calibrated_forecast_id,
                            UUID(new_calibration_by_cf[repair.calibrated_forecast_id]),
                            repair.repaired_content_hash,
                            repair.calibrated_forecast_id,
                        ),
                    )
                cur.execute(enable_calibrated)
                cur.execute(enable_calibrations)
                cur.execute(enable_outcomes)

    return _cascade_payload(outcomes_scanned=len(outcome_rows), plan=plan, apply=apply)


def main(argv: list[str] | None = None) -> int:
    load_repo_env()
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite stale ForecastOutcome content_hash/outcome_id digests. "
            "Dry-run by default; requires a privileged direct Postgres URI."
        )
    )
    parser.add_argument(
        "--postgres-uri",
        default=None,
        help="Direct Postgres URI owned by the table owner (default: env, below).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Disable the append-only trigger, rewrite the digests, re-enable, commit.",
    )
    parser.add_argument(
        "--cascade",
        action="store_true",
        help=(
            "Also rewrite the forecast_calibrations rows that cite a repaired outcome, "
            "and the calibrated_forecasts they anchor (three-table citation cascade, "
            "one transaction, all triggers disabled)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Inspect at most N outcome rows (dry-run triage / staged apply).",
    )
    args = parser.parse_args(argv)

    uri = _resolve_uri(args.postgres_uri)
    psycopg, sql, dict_row = _import_psycopg()
    connect = partial(psycopg.connect, uri, row_factory=dict_row)

    if args.cascade:
        payload = run_cascade_repair(
            connect=connect, sql_module=sql, apply=args.apply, limit=args.limit
        )
    else:
        payload = run_repair(connect=connect, sql_module=sql, apply=args.apply, limit=args.limit)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not payload["unrepairable"] else 3


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
