"""Contract tests for migration 092, private attention-context store (#2922 / WP13.2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "092_olympus_attention_context.sql"

TABLES = (
    "olympus_attention_plans",
    "olympus_attention_decisions",
    "olympus_attention_decision_attempts",
    "olympus_attention_context_manifests",
    "olympus_attention_policy_evaluations",
)
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


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {table}"
    return match.group("body")


def test_migration_is_the_only_092() -> None:
    assert sorted(MIGRATIONS_DIR.glob("092_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_091() -> None:
    assert (MIGRATIONS_DIR / "091_olympus_evidence_amendment_base_match.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_exist(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_privacy_rls_and_grants(sql: str, table: str) -> None:
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated" in sql
    assert f"REVOKE ALL ON public.{table} FROM service_role" in sql
    assert f"GRANT SELECT, INSERT ON public.{table} TO service_role" in sql


@pytest.mark.parametrize("table", TABLES)
def test_append_only_triggers(sql: str, table: str) -> None:
    assert f"reject_{table}_mutation" in sql
    assert f"BEFORE UPDATE OR DELETE ON public.{table}" in sql
    assert f"BEFORE TRUNCATE ON public.{table}" in sql


def test_decision_attempt_links_provider_telemetry(sql: str) -> None:
    body = _table_body(sql, "olympus_attention_decision_attempts")
    assert re.search(
        r"FOREIGN KEY\s*\(provider_attempt_id\)\s+REFERENCES\s+public\.olympus_provider_attempts",
        body,
        re.IGNORECASE,
    )


def test_plan_run_attempt_unique(sql: str) -> None:
    body = _table_body(sql, "olympus_attention_plans")
    assert "UNIQUE (run_id, attempt_id)" in body.replace("\n", " ")


def test_decision_plan_target_unique(sql: str) -> None:
    body = _table_body(sql, "olympus_attention_decisions")
    assert "UNIQUE (plan_id, target_key)" in body.replace("\n", " ")
