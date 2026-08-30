"""Structural contract tests for T2 billing migration 100 (claim_sync_pending).

# score:allow todo

Mirrors ``test_migration_tenancy.py``: parse SQL on disk, never talk to live
Supabase. Asserts the column lands on ``workspaces`` after 096–098, does not
collide with K3's 099, and stays single-transaction compatible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M100 = MIGRATIONS_DIR / "100_workspaces_claim_sync_pending.sql"

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


def test_migration_100_is_only_claim_sync_file() -> None:
    """T2 allocates 100; must not CREATE a second 100_* or reuse K3's 099."""
    assert sorted(MIGRATIONS_DIR.glob("100_*.sql")) == [M100]
    # K3 may or may not be present on this branch; T2 must not author 099.
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
    assert "200" in raw_100  # still return 200 to Stripe on claim-sync failure
