"""Contract tests for migration 074 — curated accounting views (#2599)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "074_olympus_accounting_views.sql"

PUBLIC_VIEWS = (
    "public_accounting_period_status",
    "public_finalized_nav",
    "public_accounting_nav_history",
    "public_daily_realized_attribution",
)

ACCOUNTING_TABLES = (
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def test_migration_is_the_only_074() -> None:
    assert sorted(MIGRATIONS_DIR.glob("074_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_073() -> None:
    assert (MIGRATIONS_DIR / "073_olympus_lookback_vs_realized.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert 74 in numbers
    assert numbers.index(73) < numbers.index(74)


@pytest.mark.parametrize("view", PUBLIC_VIEWS)
def test_public_views_are_security_definer(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(r"security_invoker\s*=\s*false", body, re.I)


def test_finalized_nav_only_final_tip(sql: str) -> None:
    body = _view_body(sql, "public_finalized_nav")
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "supersedes_id" in body
    assert "current_book_lookback" not in body
    assert "position_attribution" not in body
    assert "'finalized_accounting'" in body


def test_period_status_exposes_non_final_tips(sql: str) -> None:
    body = _view_body(sql, "public_accounting_period_status")
    assert "quality_reasons" in body
    assert "status" in body
    # Must not filter to final-only — incomplete periods stay explicit.
    assert not re.search(r"WHERE\s+p\.status\s*=\s*'final'", body, re.I)


def test_nav_history_labels_legacy_and_never_blends(sql: str) -> None:
    body = _view_body(sql, "public_accounting_nav_history")
    assert "UNION ALL" in body.upper()
    assert "'legacy_nav_history'" in body
    assert "'legacy_estimate'" in body
    assert "'finalized_accounting'" in body or "public_finalized_nav" in body
    assert "NOT EXISTS" in body.upper()


def test_public_realized_attribution_final_only(sql: str) -> None:
    body = _view_body(sql, "public_daily_realized_attribution")
    assert "olympus_accounting_contributions" in body
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "current_book_lookback" not in body
    assert "'daily_realized_attribution'" in body


@pytest.mark.parametrize("table", ACCOUNTING_TABLES)
def test_no_anon_grants_on_private_bases(sql: str, table: str) -> None:
    assert not re.search(
        rf"GRANT\s+SELECT\s+ON\s+public\.{table}\s+TO\s+(?:anon|authenticated)",
        sql,
        re.I,
    )


@pytest.mark.parametrize("view", PUBLIC_VIEWS)
def test_anon_select_granted_on_curated_views(sql: str, view: str) -> None:
    assert re.search(
        rf"GRANT\s+SELECT\s+ON\s+public\.{view}\s+TO\s+anon\s*,\s*authenticated",
        sql,
        re.I,
    )


def test_documents_shadow_cutover_gate(raw: str) -> None:
    assert "shadow" in raw.lower()
    assert "rollback" in raw.lower()


def test_074_day_return_formula_superseded_by_084() -> None:
    """074 historically used net_pnl_total/E0; #2779 / 084 replaces with equity delta.

    Keep 074 immutable (already applied). Contract for the live formula lives in
    ``test_migration_084.py``.
    """
    successor = MIGRATIONS_DIR / "084_olympus_accounting_day_return_pct.sql"
    assert successor.is_file(), "084 must replace day_return_pct with equity delta"
    body_074 = _strip_comments(MIGRATION_PATH.read_text(encoding="utf-8"))
    # Historical defect retained in 074 source for replay archaeology.
    assert re.search(r"net_pnl_total\s*/\s*p\.opening_equity", body_074, re.I)
    body_084 = _strip_comments(successor.read_text(encoding="utf-8"))
    assert re.search(
        r"(?:p\.)?closing_equity\s*-\s*(?:p\.)?opening_equity",
        body_084,
        re.I,
    )
    assert not re.search(r"net_pnl_total\s*/\s*(?:p\.)?opening_equity", body_084, re.I)
