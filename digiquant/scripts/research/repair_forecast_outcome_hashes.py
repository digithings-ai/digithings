#!/usr/bin/env python3
"""Repair stored ForecastOutcome content_hash / outcome_id digests (#4298).

Why this exists
---------------
``olympus_forecast_outcomes`` persists return fractions in Postgres ``numeric``
columns. ``numeric`` does not preserve trailing zeros, so a row written before
#4298 with the raw ``str(Decimal)`` spelling (e.g. ``0.0325``) recomputes to a
different canonical digest now that hashing is fixed at 8dp. The daily reader
fails loud on such a row, so this one-shot rewrites the two hash-bearing columns.

Append-only table
-----------------
The table is append-only (migration 080): ``reject_olympus_forecast_outcomes_mutation``
rejects UPDATE/DELETE/TRUNCATE for every role, and ``service_role`` holds
SELECT+INSERT only. The repair therefore needs a **privileged direct Postgres
URI** (``CORE_POSTGRES_URI`` or ``DATABASE_URL``) whose role owns the table —
not the PostgREST service key. The UPDATEs run in one transaction with the
mutation trigger disabled and re-enabled around them; any failure rolls the whole
transaction back, which restores the trigger on its own.

``outcome_id`` PK churn
-----------------------
Repairing the digest changes ``outcome_id`` (its UUID5 input). The
``olympus_forecast_calibrations.outcome_ids`` array cites those UUIDs and is not
a foreign key, so it would go stale. The array is, however, covered by the
calibration's immutable ``content_hash``/``calibration_id`` (and transitively by
``olympus_calibrated_forecasts.calibration_id``): an in-place array rewrite would
either invalidate the calibration digest or force a PK cascade across two more
append-only tables. This one-shot tool therefore **refuses** to repair any row
still cited by a calibration and reports it under ``unrepairable`` with the
reason — it never rewrites a row and silently leaves stale lineage (#4295 G2).
Default mode is a dry run; pass ``--apply`` to write.

Usage::

    PYTHONPATH=digiquant/src:. python digiquant/scripts/research/repair_forecast_outcome_hashes.py
    PYTHONPATH=digiquant/src:. python digiquant/scripts/research/repair_forecast_outcome_hashes.py --apply
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

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _path in (str(_REPO_ROOT / "digiquant" / "src"), str(_SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from _env import load_repo_env  # noqa: E402

from digiquant.research.forecast_outcomes import (  # noqa: E402
    OUTCOMES,
    ForecastOutcomeHashRepairPlan,
    plan_forecast_outcome_hash_repairs,
)

logger = logging.getLogger(__name__)

_TRIGGER = "reject_olympus_forecast_outcomes_mutation"
_CALIBRATIONS = "olympus_forecast_calibrations"
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
        "--limit",
        type=int,
        default=None,
        help="Inspect at most N rows (dry-run triage / staged apply).",
    )
    args = parser.parse_args(argv)

    uri = _resolve_uri(args.postgres_uri)
    psycopg, sql, dict_row = _import_psycopg()
    connect = partial(psycopg.connect, uri, row_factory=dict_row)

    payload = run_repair(connect=connect, sql_module=sql, apply=args.apply, limit=args.limit)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not payload["unrepairable"] else 3


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
