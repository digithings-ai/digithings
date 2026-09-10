"""Contract tests for migration 123 — credible-tip gate + seam marker (#3767)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "123_olympus_accounting_credible_tip_seam.sql"

TIP_VIEWS = (
    "public_accounting_period_status",
    "public_finalized_nav",
    "public_daily_realized_attribution",
)

PUBLIC_VIEWS = (
    "public_accounting_period_status",
    "public_finalized_nav",
    "public_accounting_nav_history",
    "public_daily_realized_attribution",
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


def test_migration_is_the_only_123() -> None:
    assert sorted(MIGRATIONS_DIR.glob("123_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_121() -> None:
    assert (MIGRATIONS_DIR / "121_checkpoint_blobs_nullable.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert 123 in numbers
    assert (numbers.index(122) if 122 in numbers else numbers.index(121)) < numbers.index(123)


@pytest.mark.parametrize("view", TIP_VIEWS)
def test_credible_tip_gate_ignores_zero_equity_tombstones(sql: str, view: str) -> None:
    """A superseder voids a tip only when credible (#3767 root cause 1)."""
    body = _view_body(sql, view)
    assert "supersedes_id" in body
    # Tombstone shape: incomplete/failed + zero opening and closing equity.
    assert re.search(r"status\s+IN\s*\(\s*'incomplete'\s*,\s*'failed'\s*\)", body, re.I)
    assert re.search(r"opening_equity\s*=\s*0", body, re.I)
    assert re.search(r"closing_equity\s*=\s*0", body, re.I)


@pytest.mark.parametrize("view", TIP_VIEWS)
def test_credible_tip_gate_ignores_restatement_markers(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert "superseded_by_restatement" in body
    assert "unnest" in body.lower()


@pytest.mark.parametrize("view", TIP_VIEWS)
def test_tip_views_still_require_complete_children(sql: str, view: str) -> None:
    """085 predicate retained — 123 only narrows the supersession gate."""
    body = _view_body(sql, view)
    assert "olympus_accounting_contributions" in body
    if view != "public_daily_realized_attribution":
        assert "olympus_accounting_holdings" in body or "upper" in body.lower()


def test_finalized_nav_still_final_only(sql: str) -> None:
    body = _view_body(sql, "public_finalized_nav")
    assert re.search(r"status\s*=\s*'final'", body, re.I)
    assert "cardinality" in body.lower()


def test_period_status_still_allows_non_final(sql: str) -> None:
    body = _view_body(sql, "public_accounting_period_status")
    assert not re.search(r"WHERE\s+p\.status\s*=\s*'final'", body, re.I)


def test_nav_history_exposes_series_seam(sql: str) -> None:
    """#3767 root cause 3: stitched series must mark the legacy->finalized seam."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert "series_seam" in body
    assert "UNION ALL" in body.upper()
    assert "'legacy_nav_history'" in body
    assert "'finalized_accounting'" in body or "public_finalized_nav" in body
    # Seam = first row after a source flip (lag over ordered dates).
    assert re.search(r"lag\s*\(", body, re.I)
    assert "IS DISTINCT FROM" in body.upper()


def test_nav_history_still_single_row_per_date(sql: str) -> None:
    body = _view_body(sql, "public_accounting_nav_history")
    assert "NOT EXISTS" in body.upper()


@pytest.mark.parametrize("view", PUBLIC_VIEWS)
def test_public_views_are_security_definer(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(r"security_invoker\s*=\s*false", body, re.I)


@pytest.mark.parametrize("view", PUBLIC_VIEWS)
def test_anon_select_granted_on_curated_views(sql: str, view: str) -> None:
    assert re.search(
        rf"GRANT\s+SELECT\s+ON\s+public\.{view}\s+TO\s+anon\s*,\s*authenticated",
        sql,
        re.I,
    )


def test_no_base_table_grants(sql: str) -> None:
    for table in (
        "olympus_accounting_periods",
        "olympus_accounting_contributions",
        "olympus_accounting_holdings",
    ):
        assert not re.search(
            rf"GRANT\s+SELECT\s+ON\s+public\.{table}\s+TO\s+(?:anon|authenticated)",
            sql,
            re.I,
        )


def test_documents_issue_and_view_only(raw: str) -> None:
    lower = raw.lower()
    assert "3767" in raw
    assert "tombstone" in lower
    assert "series_seam" in lower
    assert "create or replace view" in lower
