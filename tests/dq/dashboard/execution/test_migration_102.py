"""Structural contract tests for migration 102 (execution broker mirror, K4).

# score:allow todo

Pure-SQL parse checks — no database. Pins append-only privileges, RLS
deny-by-default, workspace_id FKs, deterministic-id comments, and the
renumber-at-merge header note for the 100/101 gap held by sibling T2.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "102_kairos_broker_mirror.sql"

TABLES = ("broker_orders", "broker_executions", "broker_position_snapshots")
TRIGGER_FUNCTION = "reject_broker_mirror_mutation"
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_migration_is_the_only_102(raw: str) -> None:
    assert sorted(MIGRATIONS_DIR.glob("102_*.sql")) == [MIGRATION_PATH]


def test_header_notes_renumber_at_merge(raw: str) -> None:
    assert "renumber" in raw.lower()
    assert "100" in raw and "101" in raw
    assert "T2" in raw or "sibling" in raw.lower()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None


@pytest.mark.parametrize("table", TABLES)
def test_table_created(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_workspace_id_fk(sql: str, table: str) -> None:
    body = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*\((?P<body>.*?)\n\);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert body, f"missing CREATE TABLE for {table}"
    assert re.search(
        r"workspace_id\s+uuid\s+NOT\s+NULL\s+REFERENCES\s+public\.workspaces\s*\(\s*id\s*\)",
        body.group("body"),
        re.IGNORECASE,
    )


def test_broker_orders_fk_connection(sql: str) -> None:
    assert re.search(
        r"connection_id\s+uuid\s+NOT\s+NULL\s+REFERENCES\s+public\.broker_connections",
        sql,
        re.IGNORECASE,
    )


def test_broker_connections_workspace_fk_backfill(sql: str) -> None:
    assert "broker_connections_workspace_id_fkey" in sql
    assert re.search(
        r"FOREIGN\s+KEY\s*\(\s*workspace_id\s*\)\s*REFERENCES\s+public\.workspaces",
        sql,
        re.IGNORECASE,
    )


def test_broker_executions_unique_on_fill(sql: str) -> None:
    assert re.search(
        r"UNIQUE\s*\(\s*broker_order_id\s*,\s*external_fill_id\s*\)",
        sql,
        re.IGNORECASE,
    )


def test_snapshots_unique_and_reconciliation_flag(sql: str) -> None:
    assert re.search(
        r"UNIQUE\s*\(\s*connection_id\s*,\s*as_of\s*\)",
        sql,
        re.IGNORECASE,
    )
    assert "reconciliation_diverged" in sql
    assert "reconciliation_report" in sql


def test_append_only_trigger_function(sql: str) -> None:
    assert re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.{TRIGGER_FUNCTION}\b",
        sql,
        re.IGNORECASE,
    )
    assert "append-only" in sql.lower()


@pytest.mark.parametrize("table", TABLES)
def test_mutation_and_truncate_triggers(sql: str, table: str) -> None:
    assert re.search(
        rf"BEFORE\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"BEFORE\s+TRUNCATE\s+ON\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_rls_enabled_no_policies(sql: str, table: str) -> None:
    assert re.search(
        rf"ALTER\s+TABLE\s+public\.{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
        re.IGNORECASE,
    )
    # No CREATE POLICY for these tables (deny-by-default).
    assert not re.search(
        rf"CREATE\s+POLICY\s+\S+\s+ON\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_service_role_select_insert_only(sql: str, table: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+service_role",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"GRANT\s+SELECT\s*,\s*INSERT\s+ON\s+public\.{table}\s+TO\s+service_role",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(
        rf"GRANT\s+[^;]*UPDATE[^;]*ON\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
@pytest.mark.parametrize("role", PUBLIC_ROLES)
def test_public_roles_revoked(sql: str, table: str, role: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+[^;]*\b{role}\b",
        sql,
        re.IGNORECASE,
    )


def test_deterministic_id_contract_in_header(raw: str) -> None:
    assert "uuid5" in raw.lower()
    assert "order_intent_id" in raw
    assert "external_fill_id" in raw
    assert "collide" in raw.lower() or "never duplicate" in raw.lower()
