"""Structural contract tests for migration 107 (ensure personal workspace).

Pure-SQL parse checks — no database. Pins the Observer bootstrap RPC,
auth.users trigger, service_role execute grant, and reserved system/house
refusal comments.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "107_ensure_personal_workspace.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
SYSTEM_ID = "1105372f-4109-5815-be5a-21091ccfc8ad"
HOUSE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_migration_is_the_only_107(raw: str) -> None:
    assert sorted(MIGRATIONS_DIR.glob("107_*.sql")) == [MIGRATION_PATH]


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None


def test_ensure_personal_workspace_rpc(sql: str) -> None:
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.ensure_personal_workspace\s*\(\s*p_user_id\s+uuid\s*\)",
        sql,
        re.IGNORECASE,
    )
    assert re.search(r"SECURITY\s+DEFINER", sql, re.IGNORECASE)
    assert "plan_tier" in sql.lower()
    assert "'free'" in sql
    assert "type" in sql.lower() and "'user'" in sql


def test_refuses_system_and_house_ids(sql: str) -> None:
    assert SYSTEM_ID in sql
    assert HOUSE_ID in sql
    assert "refused system/house" in sql.lower() or "system/house" in sql.lower()


def test_auth_users_trigger(sql: str) -> None:
    assert re.search(
        r"CREATE\s+TRIGGER\s+on_auth_user_created_ensure_workspace",
        sql,
        re.IGNORECASE,
    )
    assert re.search(r"AFTER\s+INSERT\s+ON\s+auth\.users", sql, re.IGNORECASE)
    assert "handle_new_auth_user_workspace" in sql


def test_service_role_execute_grant(sql: str) -> None:
    assert re.search(
        r"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.ensure_personal_workspace\s*\(\s*uuid\s*\)\s+TO\s+service_role",
        sql,
        re.IGNORECASE,
    )


def test_ensure_my_workspace_wrapper(sql: str) -> None:
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.ensure_my_workspace\s*\(\s*\)",
        sql,
        re.IGNORECASE,
    )
    assert "auth.uid()" in sql


def test_backfill_loop_for_existing_users(sql: str) -> None:
    assert "auth.users" in sql
    assert "NOT EXISTS" in sql.upper() or "not exists" in sql.lower()
    assert "ensure_personal_workspace" in sql
