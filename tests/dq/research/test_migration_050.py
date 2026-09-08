"""Unit tests for migration 050 (public portfolio views, #1461/#1462).

Hermetic pure-SQL parse checks in the ``test_migration_024.py`` mold: no
Postgres, no network. The load-bearing guarantee is the privacy allowlist —
the ``public_portfolio_positions`` view definition must never carry the
research-IP columns (user ruling 2026-07-10, #1462), so these assertions are
scoped to the CREATE VIEW bodies (the header comments and COMMENT ON strings
legitimately *name* the excluded columns).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "supabase"
    / "migrations"
    / "050_public_portfolio_views.sql"
)

EXPECTED_VIEWS = (
    "public_portfolio_positions",
    "public_nav_history",
    "public_price_latest",
)

# Research IP / risk parameters that must never appear in the positions view.
PRIVATE_POSITION_COLUMNS = (
    "rationale",
    "pm_notes",
    "thesis_id",
    "conviction",
    "stop_loss_pct",
    "target_pct_gain",
    "horizon_days",
)

PUBLIC_POSITION_COLUMNS = (
    "date",
    "ticker",
    "name",
    "category",
    "sector_bucket",
    "weight_pct",
    "entry_price",
    "entry_date",
    "current_price",
    "day_change_pct",
    "unrealized_pnl_pct",
    "since_entry_return_pct",
    "metrics_as_of",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    """Strip SQL line comments so assertions don't match header prose."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _view_body(sql: str, view: str) -> str:
    """Extract one ``CREATE OR REPLACE VIEW ... ;`` statement (comments stripped)."""
    body = _strip_comments(sql)
    match = re.search(
        rf"CREATE OR REPLACE VIEW\s+public\.{view}\b.*?;",
        body,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE OR REPLACE VIEW for {view} not found"
    return match.group(0)


@pytest.mark.unit
class TestViewsExist:
    @pytest.mark.parametrize("view", EXPECTED_VIEWS)
    def test_create_or_replace_present(self, sql: str, view: str) -> None:
        _view_body(sql, view)  # asserts internally

    @pytest.mark.parametrize("view", EXPECTED_VIEWS)
    def test_security_definer_explicit(self, sql: str, view: str) -> None:
        """Owner-rights views by design — the projection is the allowlist."""
        assert re.search(r"security_invoker\s*=\s*false", _view_body(sql, view), re.IGNORECASE)

    @pytest.mark.parametrize("view", EXPECTED_VIEWS)
    def test_commented_with_public_ruling(self, sql: str, view: str) -> None:
        body = _strip_comments(sql)
        comment = re.search(
            rf"COMMENT ON VIEW\s+public\.{view}\s+IS.*?;", body, re.DOTALL | re.IGNORECASE
        )
        assert comment, f"COMMENT ON VIEW missing for {view}"
        assert "#1462" in comment.group(0), f"view comment for {view} must cite the #1462 ruling"


@pytest.mark.unit
class TestPositionsAllowlist:
    @pytest.mark.parametrize("column", PRIVATE_POSITION_COLUMNS)
    def test_private_columns_excluded(self, sql: str, column: str) -> None:
        view = _view_body(sql, "public_portfolio_positions")
        assert not re.search(rf"\b{column}\b", view), (
            f"research-IP column {column!r} leaked into public_portfolio_positions"
        )

    @pytest.mark.parametrize("column", PUBLIC_POSITION_COLUMNS)
    def test_public_columns_present(self, sql: str, column: str) -> None:
        view = _view_body(sql, "public_portfolio_positions")
        assert re.search(rf"\b{column}\b", view), (
            f"expected public column {column!r} missing from public_portfolio_positions"
        )

    def test_latest_date_scoped(self, sql: str) -> None:
        view = _view_body(sql, "public_portfolio_positions")
        assert re.search(r"max\(date\)", view, re.IGNORECASE)


@pytest.mark.unit
class TestGrants:
    @pytest.mark.parametrize("view", EXPECTED_VIEWS)
    def test_revoke_then_grant_select(self, sql: str, view: str) -> None:
        body = _strip_comments(sql)
        revoke = re.search(rf"REVOKE ALL ON public\.{view}\s+FROM", body, re.IGNORECASE)
        grant = re.search(
            rf"GRANT SELECT ON public\.{view}\s+TO anon, authenticated", body, re.IGNORECASE
        )
        assert revoke, f"REVOKE ALL missing for {view}"
        assert grant, f"GRANT SELECT missing for {view}"
        assert revoke.start() < grant.start(), f"REVOKE must precede GRANT for {view}"

    def test_grant_is_select_only(self, sql: str) -> None:
        body = _strip_comments(sql)
        grants = re.findall(r"GRANT\s+(\w+(?:\s*,\s*\w+)*)\s+ON", body, re.IGNORECASE)
        assert grants, "no GRANT statements found"
        for privileges in grants:
            assert privileges.strip().upper() == "SELECT", f"non-SELECT grant found: {privileges}"


@pytest.mark.unit
def test_additive_only(sql: str) -> None:
    """Views + grants only — no tables created, nothing dropped or altered."""
    body = _strip_comments(sql)
    for forbidden in ("CREATE TABLE", "DROP ", "ALTER ", "TRUNCATE", "DELETE FROM", "UPDATE "):
        assert forbidden.lower() not in body.lower(), f"migration must be additive: {forbidden}"
