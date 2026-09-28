"""The db-migrate ledger rename + migration 136 (#4295) — the anti-replay contract.

``db-migrate.yml`` renamed its ledger from ``olympus_schema_migrations`` to
``digithings_schema_migrations``. The hazard the rename could reintroduce is
documented in the workflow header: the ledger is the SOLE skip gate, so a new,
empty ledger over a prod schema whose history lives only in the old table skips
nothing and replays ``001..N``. Because ``--single-transaction`` is per file, the
idempotent early files commit before the chain aborts — prod PARTIALLY
re-migrated with a ledger to match.

These tests pin the two mechanics that make the rename safe:

* a copy-forward bootstrap runs BEFORE the skip gate, in one transaction, and
  copies every ``(version, applied_at)`` row out of the old table while it still
  exists — so the gate can never read the new ledger empty;
* migration 136 drops the old table only after the new ledger exists and holds at
  least as many rows, is a no-op when the old table is already gone, and never
  drops anything else.

They are static assertions over the YAML and the SQL; there is no Postgres here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "db-migrate.yml"
MIGRATION = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "136_rename_schema_migrations_ledger.sql"
)

OLD = "olympus_schema_migrations"
NEW = "digithings_schema_migrations"

# Verbatim from the workflow (see tests/scripts/test_db_migrate_ledger_gate.py).
SELF_WRAP = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(workflow: dict) -> list[dict]:
    return workflow["jobs"]["migrate"]["steps"]


def _run(step: dict) -> str:
    return str(step.get("run", ""))


def _bootstrap(steps: list[dict]) -> str:
    matches = [_run(s) for s in steps if OLD in _run(s) and NEW in _run(s)]
    assert len(matches) == 1, (
        f"expected exactly one copy-forward bootstrap step, found {len(matches)}"
    )
    return matches[0]


def _apply(steps: list[dict]) -> str:
    matches = [_run(s) for s in steps if "for f in" in _run(s) and NEW in _run(s)]
    assert len(matches) == 1, f"expected exactly one migration-applying step, found {len(matches)}"
    return matches[0]


# --------------------------------------------------------------------------- #
# The rename is complete on the applying path
# --------------------------------------------------------------------------- #


def test_apply_step_uses_only_the_new_name(steps: list[dict]) -> None:
    apply = _apply(steps)
    assert f"CREATE TABLE IF NOT EXISTS {NEW}" in apply
    assert f"SELECT 1 FROM {NEW}" in apply
    assert apply.count(f"INSERT INTO {NEW}") == 2, "expected apply + self-wrap ledger writes"
    assert OLD not in apply, "the applying step still references the retired ledger name"


def test_old_name_is_confined_to_the_bootstrap(steps: list[dict]) -> None:
    """No step outside the bootstrap may name the old table at all."""
    naming = [i for i, s in enumerate(steps) if OLD in _run(s)]
    assert len(naming) == 1, f"{len(naming)} steps reference {OLD}; expected only the bootstrap"
    bootstrap = _run(steps[naming[0]])
    assert NEW in bootstrap
    # The bootstrap only ever READS the old table.
    for verb in ("INSERT INTO", "UPDATE", "DELETE FROM", "DROP TABLE", "ALTER TABLE"):
        assert not re.search(rf"{verb}\s+(?:public\.)?{OLD}\b", bootstrap, re.IGNORECASE), verb
    assert f"FROM public.{OLD}" in bootstrap


def test_bootstrap_copy_forward_shape(steps: list[dict]) -> None:
    bootstrap = _bootstrap(steps)
    assert "CREATE TABLE IF NOT EXISTS public." + NEW in bootstrap
    assert "ON CONFLICT (version) DO NOTHING" in bootstrap
    assert "SELECT version, applied_at" in bootstrap
    assert f"to_regclass('public.{OLD}') IS NOT NULL" in bootstrap, (
        "the copy must be guarded so a fresh environment (old table absent) is safe"
    )


# --------------------------------------------------------------------------- #
# Ordering and atomicity of the bootstrap
# --------------------------------------------------------------------------- #


def test_bootstrap_runs_before_the_skip_gate(steps: list[dict]) -> None:
    bootstrap_i = gate_i = None
    for i, s in enumerate(steps):
        run = _run(s)
        if OLD in run and NEW in run:
            bootstrap_i = i
        if f"SELECT 1 FROM {NEW}" in run:
            gate_i = i
    assert bootstrap_i is not None and gate_i is not None
    assert bootstrap_i < gate_i, (
        "the copy-forward bootstrap must run BEFORE the skip gate, or the gate can read the "
        "new ledger empty while prod's history lives only in the old table — replaying 001..N"
    )


def test_bootstrap_is_single_invocation_and_single_transaction(steps: list[dict]) -> None:
    bootstrap = _bootstrap(steps)
    assert bootstrap.count("psql ") == 1, "the bootstrap must be one psql invocation"
    assert "BEGIN;" in bootstrap and "COMMIT;" in bootstrap, "the bootstrap must be one transaction"
    assert "-v ON_ERROR_STOP=1" in bootstrap, "a failed bootstrap must abort the run, not warn"


def test_bootstrap_preserves_the_1755_ledger_lock(steps: list[dict]) -> None:
    """057 locked the old ledger; the new table must not ship unlocked (#1755)."""
    bootstrap = _bootstrap(steps)
    assert f"ALTER TABLE public.{NEW} ENABLE ROW LEVEL SECURITY;" in bootstrap
    assert f"REVOKE ALL ON public.{NEW} FROM PUBLIC, anon, authenticated;" in bootstrap


# --------------------------------------------------------------------------- #
# Migration 136: guarded, loud, unwrapped
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"missing {MIGRATION.name}"
    return MIGRATION.read_text(encoding="utf-8")


def test_migration_136_has_no_outer_transaction(sql: str) -> None:
    """db-migrate wraps unwrapped files in --single-transaction; a bare BEGIN; would break it."""
    assert not SELF_WRAP.search(sql), "136 carries its own BEGIN; and would be double-wrapped"
    assert sql.count("$$") == 2, "expected one balanced dollar-quoted DO block"


def test_migration_136_only_drops_the_old_ledger(sql: str) -> None:
    drops = re.findall(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([a-z0-9_.]+)", sql, re.IGNORECASE)
    assert drops == [f"public.{OLD}"], f"unexpected DROP TABLE target(s): {drops}"


def test_migration_136_guard_is_fail_closed_and_actionable(sql: str) -> None:
    assert "RAISE EXCEPTION" in sql, "the drop must refuse rather than guess"
    assert f"to_regclass('public.{OLD}') IS NULL" in sql, "must no-op when the old table is gone"
    assert f"to_regclass('public.{NEW}') IS NULL" in sql, "must refuse without the new ledger"
    assert "new_rows < old_rows" in sql, "must refuse when the copy has not completed"
    assert "132 -> 133 -> 134 -> 136" in sql, "the exception must name the required order"
    assert "copy-forward bootstrap" in sql, "the exception must name the prerequisite bootstrap"
    assert "RETURN;" in sql, "a fresh environment must be a no-op, not an error"


def test_migration_136_guards_the_drop(sql: str) -> None:
    guard = sql.index("new_rows < old_rows")
    drop = sql.index(f"DROP TABLE public.{OLD}")
    assert guard < drop, "the row-count guard must precede the drop"


def test_migration_136_filename(sql: str) -> None:
    assert MIGRATION.name == "136_rename_schema_migrations_ledger.sql"
