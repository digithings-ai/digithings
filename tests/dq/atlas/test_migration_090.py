"""Contract tests for migration 090, private evidence-bundle store (#2844 / WP11.1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "090_olympus_evidence_bundles.sql"

TABLES = (
    "olympus_ticker_evidence_bundles",
    "olympus_missing_fact_requests",
    "olympus_evidence_bundle_amendments",
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


def test_migration_is_the_only_090() -> None:
    assert sorted(MIGRATIONS_DIR.glob("090_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_089() -> None:
    assert (MIGRATIONS_DIR / "089_olympus_research_state_pin_temporal.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


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
    assert "reject_olympus_evidence_bundle_mutation" in sql
    assert "BEFORE UPDATE OR DELETE" in sql
    assert "BEFORE TRUNCATE" in sql


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()


def test_base_unique_on_run_ticker_content(sql: str) -> None:
    body = _table_body(sql, "olympus_ticker_evidence_bundles")
    assert "source_run_id" in body
    assert "ticker" in body
    assert "content_hash" in body
    assert re.search(
        r"UNIQUE\s*\(\s*source_run_id\s*,\s*ticker\s*,\s*content_hash\s*\)",
        body,
        re.I,
    )
    assert re.search(r"UNIQUE\s*\(\s*source_run_id\s*,\s*ticker\s*\)", body, re.I)


def test_amendment_fk_to_base_and_request(sql: str) -> None:
    body = _table_body(sql, "olympus_evidence_bundle_amendments")
    assert re.search(
        r"FOREIGN KEY\s*\(base_bundle_id\)\s+REFERENCES\s+"
        r"public\.olympus_ticker_evidence_bundles",
        body,
        re.I,
    )
    assert re.search(
        r"FOREIGN KEY\s*\(missing_fact_request_id\)\s+REFERENCES\s+"
        r"public\.olympus_missing_fact_requests",
        body,
        re.I,
    )


def test_request_fk_to_base(sql: str) -> None:
    body = _table_body(sql, "olympus_missing_fact_requests")
    assert re.search(
        r"FOREIGN KEY\s*\(base_bundle_id\)\s+REFERENCES\s+"
        r"public\.olympus_ticker_evidence_bundles",
        body,
        re.I,
    )
