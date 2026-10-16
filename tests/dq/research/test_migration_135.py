"""Unit tests for migration 135 — Phase C olympus_* compat-view drop (#4295 G5).

Migration 135 is the final phase of the ``olympus_*`` terminology removal. It
drops the old-name compatibility VIEWS that Phase B (migration 134) recreated
after renaming the base objects, so the old vocabulary disappears from the
database. These tests pin the safety properties the Phase C design depends on:

* only regular views (relkind = 'v') are dropped, and never a base table;
* ``DROP VIEW`` is issued without ``CASCADE`` so a dependent object fails loudly;
* ``olympus_schema_migrations`` is never a drop target (it is excluded by name in
  both the guard and the drop loop);
* the loud safety guard RAISEs when an ``olympus_*`` TABLE still exists, naming
  the required order 132 -> 134 -> 135;
* the drop is dynamic (catalogue iteration + ``format('%I.%I', ...)``) so it does
  not depend on Phase B's exact object list;
* the file is plain SQL, self-wrap free, and never touches the ledger.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M135 = MIGRATIONS_DIR / "135_rename_phase_c_drop_compat_views.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
DROP_REGEX = re.compile(r"\bdrop\s+([a-z]+)")


def _strip_comments(sql: str) -> str:
    """Return ``sql`` with ``--`` line comments removed.

    The migration header deliberately names the hazards it avoids (for example
    "base TABLES are never touched"), so a naive substring scan would flag its
    own documentation. Strip comments before asserting on the executable SQL.
    """
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


@pytest.fixture(scope="module")
def sql() -> str:
    assert M135.is_file(), f"missing {M135.name}"
    return M135.read_text()


@pytest.fixture(scope="module")
def code(sql: str) -> str:
    return _strip_comments(sql)


@pytest.fixture(scope="module")
def lowered(code: str) -> str:
    return code.lower()


def test_is_plain_sql_without_a_transaction_wrapper(lowered: str) -> None:
    assert not SELF_WRAP_REGEX.search(lowered)
    assert "commit;" not in lowered
    assert "rollback;" not in lowered


def test_only_views_are_dropped(lowered: str) -> None:
    drops = DROP_REGEX.findall(lowered)
    assert drops, "expected at least one DROP statement"
    assert set(drops) <= {"view"}, drops
    assert "drop table" not in lowered


def test_drop_is_never_cascading(lowered: str) -> None:
    assert "cascade" not in lowered


def test_targets_are_limited_to_the_public_schema(lowered: str) -> None:
    assert "n.nspname = 'public'" in lowered
    assert "pg_catalog.pg_namespace" in lowered


def test_only_regular_views_are_targeted(lowered: str) -> None:
    assert "pg_catalog.pg_class" in lowered
    assert "relkind = 'v'" in lowered
    assert "relkind = 'r'" in lowered  # the guard looks for leftover tables


def test_matches_only_the_olympus_prefix_with_an_escaped_underscore(sql: str) -> None:
    # Both the guard and the drop loop use the escaped-underscore LIKE pattern,
    # so `olympusfoo` is not swept up and only names beginning `olympus_` match.
    assert sql.count("LIKE 'olympus\\_%'") == 2


def test_drop_is_dynamic_and_quote_ident_safe(lowered: str) -> None:
    assert "execute format(" in lowered
    assert "drop view %i.%i" in lowered
    assert "%i" in lowered


def test_never_drops_the_ledger(lowered: str) -> None:
    assert not re.search(
        r"drop\s+(table|view|schema|function|materialized\s+view)\s+"
        r"(public\.)?olympus_schema_migrations",
        lowered,
    )
    assert "rename to olympus_schema_migrations" not in lowered
    assert "alter table olympus_schema_migrations" not in lowered
    assert "alter table public.olympus_schema_migrations" not in lowered


def test_ledger_is_excluded_from_guard_and_drop_loop(sql: str) -> None:
    assert sql.count("<> 'olympus_schema_migrations'") == 2


def test_safety_guard_raises_when_olympus_tables_remain(lowered: str) -> None:
    assert "raise exception" in lowered
    assert "olympus_* base table(s) still present" in lowered


def test_safety_guard_names_the_required_order(sql: str) -> None:
    assert "132 -> 134 -> 135" in sql


def test_drop_loop_orders_results_for_determinism(lowered: str) -> None:
    assert "order by c.relname" in lowered


def test_never_renames_or_alters_objects(code: str) -> None:
    lowered = code.lower()
    assert "rename to" not in lowered
    assert "alter table" not in lowered
    assert "alter view" not in lowered
