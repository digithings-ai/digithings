"""Structural contract tests for migration 112 (product invite codes)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "112_product_invite_codes.sql"


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    raw = MIGRATION_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_112() -> None:
    assert sorted(MIGRATIONS_DIR.glob("112_*.sql")) == [MIGRATION_PATH]


def test_does_not_reuse_reserved_111() -> None:
    assert list(MIGRATIONS_DIR.glob("111_*.sql")) == []


def test_creates_hashed_invite_tables(sql: str) -> None:
    for table in (
        "product_invite_codes",
        "product_invite_redemptions",
        "product_invite_attempts",
    ):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in sql
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated" in sql


def test_hash_is_sha256_hex_and_service_role_only(sql: str) -> None:
    assert "code_hash ~ '^[0-9a-f]{64}$'" in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.product_invite_codes "
        "TO service_role"
    ) in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.product_invite_codes TO anon"
        not in sql
    )
    assert "NEXT_PUBLIC" not in sql
