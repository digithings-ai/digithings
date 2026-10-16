"""Contract tests for migration 089, research-state pin temporal CHECKs (#2867)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "digiquant"
    / "supabase"
    / "migrations"
    / "089_olympus_research_state_pin_temporal.sql"
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return _strip_comments(MIGRATION_PATH.read_text(encoding="utf-8"))


def test_adds_pin_temporal_check(sql: str) -> None:
    assert re.search(
        r"ADD\s+CONSTRAINT\s+chk_olympus_research_state_pins_temporal",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        r"requested_as_of\s*<=\s*knowledge_cutoff_at",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        r"knowledge_cutoff_at\s*<=\s*pinned_at",
        sql,
        re.IGNORECASE,
    )


def test_idempotent_drop_before_add(sql: str) -> None:
    assert re.search(
        r"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+chk_olympus_research_state_pins_temporal",
        sql,
        re.IGNORECASE,
    )
