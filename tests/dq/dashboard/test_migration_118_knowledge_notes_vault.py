"""Migration 118 — knowledge_notes vault namespace (#1142)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = REPO_ROOT / "digiquant" / "supabase" / "migrations" / "118_knowledge_notes_vault_namespace.sql"


def test_migration_118_adds_vault_namespace_and_composite_unique() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "create table if not exists public.knowledge_notes" in sql
    assert "vault         text not null default 'finance'" in sql or (
        "vault text not null default 'finance'" in sql.replace("\n", " ")
    )
    assert "add column if not exists vault text not null default 'finance'" in sql
    assert "drop constraint if exists knowledge_notes_vault_path_key" in sql
    assert "knowledge_notes_vault_vault_path_key" in sql
    assert "knowledge_notes_vault_slug_key" in sql
    assert "unique (vault, vault_path)" in sql
    assert "unique (vault, slug)" in sql
    assert "Service-role-only" in sql or "service-role-only" in sql.lower()
    assert "#1142" in sql
