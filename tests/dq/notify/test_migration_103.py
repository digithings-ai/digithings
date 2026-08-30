"""Structural contract tests for migration 103 (K5 notification_prefs + notification_log)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "103_notification_prefs.sql"

TABLES = ("notification_prefs", "notification_log")
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


def test_migration_is_the_only_103(raw: str) -> None:
    assert sorted(MIGRATIONS_DIR.glob("103_*.sql")) == [MIGRATION_PATH]


def test_header_notes_renumber_at_merge(raw: str) -> None:
    assert "renumber" in raw.lower()
    assert "100" in raw or "101" in raw or "099" in raw or "102" in raw


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None


@pytest.mark.parametrize("table", TABLES)
def test_table_created(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


def test_notification_prefs_workspace_fk(sql: str) -> None:
    body = re.search(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.notification_prefs\s*\((?P<body>.*?)\n\);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert body
    assert re.search(
        r"workspace_id\s+uuid\s+PRIMARY\s+KEY\s+REFERENCES\s+public\.workspaces",
        body.group("body"),
        re.IGNORECASE,
    )


def test_notification_log_pk(sql: str) -> None:
    assert re.search(
        r"PRIMARY\s+KEY\s*\(\s*workspace_id\s*,\s*event_key\s*,\s*sent_date\s*\)",
        sql,
        re.IGNORECASE,
    )


def test_notification_log_append_only(sql: str) -> None:
    assert "GRANT SELECT, INSERT ON public.notification_log" in sql.replace("\n", " ")


def test_notification_prefs_digest_hour_check(sql: str) -> None:
    assert "digest_hour_utc BETWEEN 0 AND 23" in sql


def test_notification_log_append_only_triggers(sql: str) -> None:
    assert "reject_notification_log_mutation" in sql
    assert re.search(
        r"BEFORE\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.notification_log",
        sql,
        re.IGNORECASE,
    )
