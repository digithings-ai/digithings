"""Contract tests for migration 091, amendment base/request match (#2895)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "091_olympus_evidence_amendment_base_match.sql"
PRIOR_PATH = MIGRATIONS_DIR / "090_olympus_evidence_bundles.sql"

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


def test_migration_is_the_only_091() -> None:
    assert sorted(MIGRATIONS_DIR.glob("091_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_090() -> None:
    assert PRIOR_PATH.is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()


def test_base_mismatch_function_and_trigger(sql: str) -> None:
    assert "reject_olympus_evidence_amendment_base_mismatch" in sql
    assert re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.reject_olympus_evidence_amendment_base_mismatch",
        sql,
        re.I,
    )
    assert re.search(
        r"BEFORE\s+INSERT\s+OR\s+UPDATE\s+ON\s+public\.olympus_evidence_bundle_amendments",
        sql,
        re.I,
    )
    assert "request_base <> NEW.base_bundle_id" in sql or (
        "request_base" in sql and "NEW.base_bundle_id" in sql
    )


def test_architecture_conflict_markers_cleared() -> None:
    arch = (REPO_ROOT / "digiquant" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "<<<<<<<" not in arch
    assert ">>>>>>>" not in arch
    assert "Ticker evidence bundles (#2844 / WP11.1" in arch
    assert "research_state_store" in arch and "unwired" in arch
    assert "091" in arch
