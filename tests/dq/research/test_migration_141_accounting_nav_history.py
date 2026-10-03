"""Migration 141 stops public_accounting_nav_history publishing every book.

123 left the view security_invoker=false and granted it to anon. Owner rights
skip the house-only policy on nav_history, and public_finalized_nav had no
workspace predicate, so a private period or a later private NAV date landed
on the public series. Static parse only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "141_accounting_nav_history_house_scope.sql"
HOUSE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return _strip_comments(MIGRATION.read_text(encoding="utf-8"))


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def test_migration_141_is_only_141() -> None:
    assert sorted(MIGRATIONS.glob("141_*.sql")) == [MIGRATION]


def test_history_view_is_security_invoker(sql: str) -> None:
    """Definer plus anon SELECT was the leak. The public chart still has SELECT."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)
    assert "ALTER VIEW public.public_accounting_nav_history SET (security_invoker = true);" in sql
    assert re.search(
        r"GRANT\s+SELECT\s+ON\s+public\.public_accounting_nav_history\s+TO\s+anon\s*,\s*authenticated",
        sql,
        re.I,
    )


def test_finalized_nav_stays_definer_but_house_scoped(sql: str) -> None:
    body = _view_body(sql, "public_finalized_nav")
    assert re.search(r"security_invoker\s*=\s*false", body, re.I)
    assert "ALTER VIEW public.public_finalized_nav SET (security_invoker = false);" in sql
    assert HOUSE_ID in body
    assert re.search(r"p\.workspace_id\s*=", body, re.I)
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "cardinality" in body.lower()


def test_legacy_nav_window_is_house_only(sql: str) -> None:
    """Lag must run on house rows, not on a later private book's NAV."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert "series_seam" in body
    assert "UNION ALL" in body.upper()
    assert "'legacy_nav_history'" in body
    match = re.search(
        r"FROM\s+public\.nav_history\s+n\s+WHERE\s+n\.workspace_id\s*=\s*'" + HOUSE_ID + r"'",
        body,
        flags=re.IGNORECASE,
    )
    assert match, "nav_history scan must filter house workspace before the window"
    assert "lag(" in body.lower()


def test_no_anon_grant_on_accounting_bases(sql: str) -> None:
    for table in (
        "olympus_accounting_periods",
        "olympus_accounting_contributions",
        "olympus_accounting_holdings",
        "accounting_periods",
        "accounting_contributions",
        "accounting_holdings",
    ):
        assert not re.search(
            rf"GRANT\s+SELECT\s+ON\s+(?:public\.)?{table}\s+TO\s+(?:anon|authenticated)",
            sql,
            re.I,
        )


def test_does_not_touch_cutover_113(sql: str) -> None:
    assert "113_drop" not in sql
    assert "drop constraint" not in sql.lower()
