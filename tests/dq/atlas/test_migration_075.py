"""Contract tests for migration 075, PipelineProfile / ProfileConfig seam (#2607)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "075_olympus_pipeline_profiles.sql"
TABLE = "olympus_pipeline_profiles"
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


def test_migration_is_the_only_075() -> None:
    assert sorted(MIGRATIONS_DIR.glob("075_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_074() -> None:
    assert (MIGRATIONS_DIR / "074_olympus_accounting_views.sql").is_file()
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert numbers[-1] == 75
    assert 74 in numbers
    assert 75 in numbers


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_table_exists(sql: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{TABLE}\b",
        sql,
        re.IGNORECASE,
    )


def test_house_identity_check(sql: str) -> None:
    assert "chk_olympus_pipeline_profiles_house_identity" in sql
    assert "digithings-house" in sql
    assert "digithings-house-run" in sql


def test_one_house_unique_index(sql: str) -> None:
    assert "uq_olympus_pipeline_profiles_one_house" in sql


def test_house_seed(sql: str) -> None:
    assert re.search(
        r"INSERT\s+INTO\s+public\.olympus_pipeline_profiles",
        sql,
        re.IGNORECASE,
    )
    assert "digithings house ETF baseline" in sql
    assert "ON CONFLICT (profile_id) DO NOTHING" in sql


def test_house_immutable_trigger(sql: str) -> None:
    assert "reject_olympus_pipeline_profile_house_mutation" in sql
    assert re.search(
        rf"BEFORE\s+UPDATE\s+OR\s+DELETE\s+ON\s+public\.{TABLE}",
        sql,
        re.IGNORECASE,
    )


def test_rls_enabled_with_no_policies(sql: str) -> None:
    assert re.search(
        rf"ALTER\s+TABLE\s+public\.{TABLE}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(rf"CREATE\s+POLICY\b[^;]*{TABLE}", sql, re.IGNORECASE)


@pytest.mark.parametrize("role", PUBLIC_ROLES)
def test_client_roles_fully_revoked(sql: str, role: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+[^\n]*\b{role}\b",
        sql,
        re.IGNORECASE,
    )


def test_service_role_select_insert_update(sql: str) -> None:
    assert re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"GRANT\s+SELECT\s*,\s*INSERT\s*,\s*UPDATE\s+ON\s+public\.{TABLE}\s+TO\s+service_role\b",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(
        rf"GRANT\s+[^;]*\b(?:DELETE|TRUNCATE)\b[^;]*ON\s+public\.{TABLE}\b",
        sql,
        re.IGNORECASE,
    )


def test_no_public_views(sql: str) -> None:
    assert not re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\b", sql, re.IGNORECASE)


def test_header_declares_invariants(raw: str) -> None:
    header = raw.split("CREATE TABLE", 1)[0].lower()
    assert "house" in header
    assert "immutable" in header
    assert "investmentprofile" in header.replace(" ", "") or "not" in header
