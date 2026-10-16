"""Unit tests for migration 137 — atlas/h8 object rename (#4471 W3).

Migration 137 follows the 132/134/135 precedent: rename the base object, rename
its indexes / constraints / triggers, and leave a read-compat VIEW under the old
name. These tests pin the safety properties the design depends on:

* each base object is renamed exactly once and no table is created or dropped;
* every old-name compat view is a single-table ``SELECT *`` view (auto-updatable,
  so a not-yet-redeployed writer's plain INSERT still lands);
* the base-table compat views use ``security_invoker = true``; the curated health
  view keeps the original ``security_invoker = false`` (its column projection is
  the allowlist, and 060 revoked writes);
* ``atlas_run_diagnostics`` carries ``UPDATE`` for service_role because the
  legacy writer's ``INSERT ... ON CONFLICT DO UPDATE`` needs it, while
  ``h8_risk_run_refs`` stays SELECT/INSERT (the registry only INSERTs);
* anon/authenticated never gain a write privilege on an old-name view;
* the file does not touch the schema-migrations ledger and is not self-wrapped in
  a transaction (db-migrate would otherwise take the non-atomic path).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M137 = MIGRATIONS_DIR / "137_rename_atlas_and_h8_objects.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])(begin|commit)[\s]*;", re.IGNORECASE)

# new base object -> old name left behind as a compat view
BASE_RENAMES = {
    "atlas_run_diagnostics": "run_diagnostics",
    "h8_risk_run_refs": "sizing_risk_run_refs",
}

# old compat view -> (new relation, security_invoker setting)
COMPAT_VIEWS = {
    "atlas_run_diagnostics": ("run_diagnostics", "true"),
    "atlas_run_health": ("run_health", "false"),
    "h8_risk_run_refs": ("sizing_risk_run_refs", "true"),
}

INDEX_RENAMES = {
    "atlas_run_diagnostics_run_date_idx": "idx_run_diagnostics_run_date",
    "atlas_run_diagnostics_created_at_idx": "idx_run_diagnostics_created_at",
    "idx_h8_risk_run_refs_run_date": "idx_sizing_risk_run_refs_run_date",
}

RENAME_TABLE_RE = re.compile(
    r"ALTER TABLE (?:IF EXISTS )?public\.([a-z0-9_]+) RENAME TO ([a-z0-9_]+);"
)
RENAME_INDEX_RE = re.compile(
    r"ALTER INDEX (?:IF EXISTS )?public\.([a-z0-9_]+)\s+RENAME TO ([a-z0-9_]+);"
)
CONSTRAINT_PAIR_RE = re.compile(
    r"\('(h8_risk_run_refs_pkey|olympus_h8_risk_run_refs_[a-z_]+|fk_h8_risk_run_refs_[a-z]+)',\s*'([a-z_]+)'\)"
)
TRIGGER_PAIR_RE = re.compile(r"\('(reject_(?:olympus_)?h8_risk_run_refs_[a-z]+)',\s*'([a-z_]+)'\)")


@pytest.fixture(scope="module")
def sql() -> str:
    assert M137.is_file(), f"missing {M137.name}"
    return M137.read_text()


def test_renames_each_base_object_exactly_once(sql: str) -> None:
    renames = RENAME_TABLE_RE.findall(sql)
    assert dict(renames) == BASE_RENAMES
    assert len(renames) == len(BASE_RENAMES)


def test_never_creates_or_drops_a_table(sql: str) -> None:
    lowered = sql.lower()
    assert "create table" not in lowered
    assert "drop table" not in lowered


def test_renames_indexes(sql: str) -> None:
    assert dict(RENAME_INDEX_RE.findall(sql)) == INDEX_RENAMES


def test_renames_constraints_and_triggers_to_sizing_names(sql: str) -> None:
    # The pkey and the inline CHECK still carry their 081 `olympus_*` names on a
    # prod database (134 renamed only the FKs), so both spellings are accepted.
    constraint_targets = {new for _old, new in CONSTRAINT_PAIR_RE.findall(sql)}
    assert "sizing_risk_run_refs_pkey" in constraint_targets
    assert "sizing_risk_run_refs_source_run_id_check" in constraint_targets
    assert "fk_sizing_risk_run_refs_policy" in constraint_targets
    assert "fk_sizing_risk_run_refs_snapshot" in constraint_targets
    assert all(
        new.startswith("sizing_risk_run_refs") or new.startswith("fk_sizing")
        for new in constraint_targets
    )

    trigger_targets = {new for _old, new in TRIGGER_PAIR_RE.findall(sql)}
    assert trigger_targets == {
        "reject_sizing_risk_run_refs_mutation",
        "reject_sizing_risk_run_refs_truncate",
    }


def test_compat_views_are_single_table_select_star(sql: str) -> None:
    created = {
        name: (source, invoker)
        for name, invoker, source in re.findall(
            r"CREATE (?:OR REPLACE )?VIEW public\.([a-z0-9_]+)\s+"
            r"WITH \(security_invoker = (true|false)\) AS\s+"
            r"SELECT \* FROM public\.([a-z0-9_]+);",
            sql,
        )
    }
    for old, expected in COMPAT_VIEWS.items():
        assert created.get(old) == expected, old
    # nothing else is created as a view
    assert set(created) == set(COMPAT_VIEWS)


def test_compat_view_grants_match_the_legacy_writer(sql: str) -> None:
    # Upserts need UPDATE; plain INSERTs do not.
    assert "GRANT SELECT, INSERT, UPDATE ON public.atlas_run_diagnostics TO service_role;" in sql
    assert "GRANT SELECT, INSERT ON public.h8_risk_run_refs TO service_role;" in sql
    for view in COMPAT_VIEWS:
        assert (
            f"REVOKE ALL ON public.{view}\n    FROM PUBLIC, anon, authenticated, service_role;"
            in sql
        ), view


def test_anon_and_authenticated_never_gain_writes(sql: str) -> None:
    forbidden = re.compile(
        r"GRANT[^\n]*\b(INSERT|UPDATE|DELETE|TRUNCATE)\b[^\n]*\bTO\b[^\n]*\b(anon|authenticated)",
        re.IGNORECASE,
    )
    assert not forbidden.search(sql)
    for view in ("run_health", "atlas_run_health"):
        assert f"GRANT SELECT ON public.{view} TO anon, authenticated" in sql, view


def test_never_touches_the_ledger(sql: str) -> None:
    lowered = sql.lower()
    for ledger in ("digithings_schema_migrations", "schema_migrations"):
        assert f"insert into {ledger}" not in lowered
        assert f"alter table public.{ledger}" not in lowered
        assert f"drop table {ledger}" not in lowered
        assert f"rename to {ledger}" not in lowered


def test_no_self_wrapping_transaction(sql: str) -> None:
    # DO $$ ... BEGIN ... END $$ blocks are fine; a bare `begin;` is not.
    assert not SELF_WRAP_REGEX.search(sql)


def test_health_view_comment_documents_the_invoker_choice(sql: str) -> None:
    assert "COMMENT ON VIEW public.run_health IS" in sql
    assert "security_invoker = " in sql
