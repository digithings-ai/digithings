"""Structural contract tests for T2 billing migrations 100–101.

# score:allow todo

Mirrors ``test_migration_tenancy.py``: parse SQL on disk, never talk to live
Supabase. Covers claim_sync_pending (100), applied_at + last_stripe_event_created
+ column-level UPDATE grant (101).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M100 = MIGRATIONS_DIR / "100_workspaces_claim_sync_pending.sql"
M101 = MIGRATIONS_DIR / "101_stripe_webhook_applied_and_ordering.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw_100() -> str:
    assert M100.is_file(), f"migration missing: {M100}"
    return M100.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_100(raw_100: str) -> str:
    return _strip_comments(raw_100)


@pytest.fixture(scope="module")
def raw_101() -> str:
    assert M101.is_file(), f"migration missing: {M101}"
    return M101.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_101(raw_101: str) -> str:
    return _strip_comments(raw_101)


def test_migration_100_is_only_claim_sync_file() -> None:
    """T2 allocates 100; must not CREATE a second 100_* or reuse K3's 099."""
    assert sorted(MIGRATIONS_DIR.glob("100_*.sql")) == [M100]
    for path in MIGRATIONS_DIR.glob("099_*.sql"):
        assert "broker" in path.name or "credential" in path.name or "vault" in path.name, (
            f"unexpected 099 file owned by T2: {path.name}"
        )


def test_migration_100_single_transaction_compatible(raw_100: str) -> None:
    assert SELF_WRAP_REGEX.search(raw_100) is None
    assert "COMMIT;" not in raw_100.upper()


def test_100_adds_claim_sync_pending_boolean_default_false(sql_100: str) -> None:
    assert re.search(
        r"ALTER\s+TABLE\s+public\.workspaces\s+"
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+claim_sync_pending\s+"
        r"boolean\s+NOT\s+NULL\s+DEFAULT\s+false",
        sql_100,
        re.IGNORECASE,
    )


def test_100_documents_t2_retry_semantics(raw_100: str) -> None:
    lowered = raw_100.lower()
    assert "claim_sync_pending" in lowered
    assert "app_metadata" in lowered or "plan_tier" in lowered
    assert "200" in raw_100


def test_migration_101_is_only_applied_ordering_file() -> None:
    assert sorted(MIGRATIONS_DIR.glob("101_*.sql")) == [M101]


def test_migration_101_single_transaction_compatible(raw_101: str) -> None:
    assert SELF_WRAP_REGEX.search(raw_101) is None
    assert "COMMIT;" not in raw_101.upper()


def test_101_adds_applied_at_on_stripe_events(sql_101: str) -> None:
    assert re.search(
        r"ALTER\s+TABLE\s+public\.stripe_events\s+"
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+applied_at\s+timestamptz",
        sql_101,
        re.IGNORECASE,
    )


def test_101_column_level_update_grant_on_applied_at_only(sql_101: str) -> None:
    assert re.search(
        r"GRANT\s+UPDATE\s*\(\s*applied_at\s*\)\s+ON\s+public\.stripe_events\s+TO\s+service_role",
        sql_101,
        re.IGNORECASE,
    )
    # Must not widen to full-table UPDATE on stripe_events.
    assert not re.search(
        r"GRANT\s+UPDATE\s+ON\s+public\.stripe_events\s+TO\s+service_role",
        sql_101,
        re.IGNORECASE,
    )


def test_101_adds_last_stripe_event_created_on_workspaces(sql_101: str) -> None:
    assert re.search(
        r"ALTER\s+TABLE\s+public\.workspaces\s+"
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+last_stripe_event_created\s+bigint",
        sql_101,
        re.IGNORECASE,
    )


def test_101_documents_poison_pill_and_cas(raw_101: str) -> None:
    lowered = raw_101.lower()
    assert "applied_at" in lowered
    assert "poison" in lowered or "retry" in lowered
    assert "last_stripe_event_created" in lowered
    assert "cas" in lowered or "concurrent" in lowered
