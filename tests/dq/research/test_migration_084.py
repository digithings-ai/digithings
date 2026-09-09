"""Contract tests for migration 084 — equity-delta day_return_pct (#2779)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "084_olympus_accounting_day_return_pct.sql"

VIEWS = (
    "public_accounting_period_status",
    "public_finalized_nav",
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


def test_migration_is_the_only_084() -> None:
    assert sorted(MIGRATIONS_DIR.glob("084_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_083() -> None:
    assert (MIGRATIONS_DIR / "083_olympus_pretrade_risk_reports.sql").is_file()


@pytest.mark.parametrize("view", VIEWS)
def test_day_return_uses_equity_delta_not_net_pnl_alone(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(
        r"(?:p\.)?closing_equity\s*-\s*(?:p\.)?opening_equity",
        body,
        re.I,
    ), f"{view} must use (closing_equity - opening_equity) / opening_equity"
    # Must not regress to net_pnl_total / opening_equity (omits cash_pnl).
    assert not re.search(
        r"net_pnl_total\s*/\s*(?:p\.)?opening_equity",
        body,
        re.I,
    ), f"{view} must not compute day_return from net_pnl_total alone"


@pytest.mark.parametrize("view", VIEWS)
def test_views_remain_security_definer(sql: str, view: str) -> None:
    body = _view_body(sql, view)
    assert re.search(r"security_invoker\s*=\s*false", body, re.I)


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


def test_documents_equity_identity(raw: str) -> None:
    lower = raw.lower()
    assert "cash_pnl" in lower or "equity" in lower
    assert "2779" in raw
