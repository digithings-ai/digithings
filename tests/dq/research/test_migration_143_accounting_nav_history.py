"""Migration 143 stops public_accounting_nav_history mixing two NAV scales.

141 stitched house `nav_history` (legacy estimate, NAV ~100) under the
finalized accounting series (NAV ~122) with a per-date fallback, so a chart
read a sawtooth at 29 Sep and 3-4 Oct that no account ever produced. 141 also
let the 26 Aug opening-balance period (cash 100%, invested 0, day_return 0,
NAV 15.13) through as the first series row, which draws a phantom +577.3%
move on 27 Aug.

143 re-points the history view at the finalized accounting series only and
drops the seed row. The series is the accounting scale or it is nothing; the
base-100 continuity index is the plottable series until it is whole.
Static parse only, matching the 141 guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "143_accounting_nav_history_finalized_only.sql"
PRIOR = MIGRATIONS / "141_accounting_nav_history_house_scope.sql"
HOUSE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"

# The column list CREATE OR REPLACE VIEW may not change: names and order.
EXPECTED_COLUMNS = [
    "date",
    "nav",
    "cash_pct",
    "invested_pct",
    "day_return_pct",
    "source",
    "contract",
    "series_seam",
]


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return _strip_comments(MIGRATION.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def prior() -> str:
    assert PRIOR.is_file(), f"prior migration missing: {PRIOR}"
    return _strip_comments(PRIOR.read_text(encoding="utf-8"))


def _view_body(sql: str, view: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


def _selected_columns(body: str) -> list[str]:
    """Top-level select aliases of the outer SELECT of a view body."""
    head = re.match(
        r"CREATE OR REPLACE VIEW\s+public\.\w+\s*WITH\s*\([^)]*\)\s*AS\s*SELECT\s+(.*?)\s+FROM\b",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert head, "view body must start with SELECT ... FROM"
    aliases: list[str] = []
    for clause in head.group(1).split(","):
        match = re.search(r"\bAS\s+(\w+)\s*$", clause.strip(), flags=re.IGNORECASE)
        if match:
            aliases.append(match.group(1).lower())
    return aliases


def test_migration_143_is_only_143() -> None:
    assert sorted(MIGRATIONS.glob("143_*.sql")) == [MIGRATION]


def test_history_view_reads_only_the_finalized_series(sql: str) -> None:
    """No legacy estimate may reach the public series again."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert "UNION" not in body.upper(), "the history view must not union a second scale"
    assert "nav_history" not in body.lower().replace("public_accounting_nav_history", "")
    assert "legacy_estimate" not in body
    assert "legacy_nav_history" not in body
    assert re.search(r"FROM\s+public\.public_finalized_nav\b", body, re.I)


def test_history_view_never_falls_back_per_date(sql: str) -> None:
    """141's defect, named: legacy filled any date finalized was missing."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert not re.search(r"NOT\s+EXISTS", body, re.I), "per-date fallback predicate removed"
    assert not re.search(r"coalesce", body, re.I)
    assert not re.search(r"f\.date\s*=\s*legacy\.date", body, re.I)


def test_seed_row_is_excluded_and_only_the_first_row(sql: str) -> None:
    """26 Aug 15.13 is the opening balance, not a +577.3% day."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert re.search(r"row_number\s*\(\s*\)\s*OVER\s*\(\s*ORDER BY", body, re.I), (
        "the seed rule must be positional (first row of the series)"
    )
    assert re.search(r"series_position\s*=\s*1", body, re.I)
    for shape in (r"cash_pct\s*=\s*100", r"invested_pct\s*=\s*0", r"day_return_pct\s*=\s*0"):
        assert re.search(shape, body, re.I), shape
    # A later 100%-cash flat day is a real observation and must survive.
    assert re.search(r"series_position\s*=\s*1[^;]*AND[^;]*cash_pct", body, re.I | re.DOTALL)
    assert "NOT" in body


def test_column_list_and_invariants_are_preserved(sql: str) -> None:
    """CREATE OR REPLACE VIEW cannot change names or order."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert _selected_columns(body) == EXPECTED_COLUMNS
    assert re.search(r"security_invoker\s*=\s*true", body, re.I)
    assert "security_barrier" not in body.lower()
    assert "ALTER VIEW public.public_accounting_nav_history SET (security_invoker = true);" in sql
    assert re.search(
        r"GRANT\s+SELECT\s+ON\s+public\.public_accounting_nav_history\s+TO\s+anon\s*,\s*authenticated",
        sql,
        re.I,
    )
    assert re.search(
        r"GRANT\s+SELECT\s+ON\s+public\.public_accounting_nav_history\s+TO\s+service_role",
        sql,
        re.I,
    )


def test_series_seam_column_stays_and_is_now_constant(sql: str) -> None:
    """One series cannot seam. The column stays so consumers keep compiling."""
    body = _view_body(sql, "public_accounting_nav_history")
    assert re.search(r"false\s*::?\s*boolean\s+AS\s+series_seam", body, re.I)
    assert "lag(" not in body.lower()


def test_comment_no_longer_promises_the_fallback(sql: str) -> None:
    raw = MIGRATION.read_text(encoding="utf-8")
    # The string literal contains internal semicolons ("#2599; seam #3767"), so a
    # `.*?;` window stops at the first one and sees only the opening fragment --
    # a guard that cannot reach the sentence it forbids. Match the run of
    # single-quoted literals instead, then prove the window reached the end.
    comment = re.search(
        r"COMMENT\s+ON\s+VIEW\s+public\.public_accounting_nav_history\s+IS\s+((?:'[^']*'\s*)+);",
        raw,
        re.S | re.I,
    )
    assert comment, "the view comment must be restated"
    text = comment.group(1).lower()
    assert "anon select remains" in text, "comment window truncated before its end"
    assert "preferred" not in text
    assert "other dates" not in text
    assert "finalized" in text


def test_143_does_not_redefine_the_definer_projection(sql: str) -> None:
    """public_finalized_nav stays 141's security-definer, house-scoped base."""
    with pytest.raises(AssertionError):
        _view_body(sql, "public_finalized_nav")


def test_143_leaves_141_and_142_applied_files_alone(sql: str, prior: str) -> None:
    """The ledger is per filename; an applied migration never re-runs."""
    assert "141_" not in sql
    assert "142_" not in sql
    assert "UNION ALL" in prior.upper(), "control: 141 still carries the union"


def test_no_anon_grant_on_accounting_bases(sql: str) -> None:
    for table in ("accounting_periods", "accounting_contributions", "accounting_holdings"):
        assert not re.search(
            rf"GRANT\s+SELECT\s+ON\s+(?:public\.)?{table}\s+TO\s+(?:anon|authenticated)",
            sql,
            re.I,
        )


def test_does_not_touch_cutover_113(sql: str) -> None:
    assert "113_drop" not in sql
    assert "drop constraint" not in sql.lower()
    assert HOUSE_ID not in sql, "143 reads the house-scoped view, it does not re-scope"
