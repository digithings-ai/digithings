"""Structural checks for WP1 join + nullable usage on olympus_run_events (#2763)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "086_olympus_run_events_wp1_join.sql"
)
JOIN_COLUMNS = {"call_id", "attempt_id", "node_run_id"}
PUBLIC_BASE = {
    "run_id",
    "attempt",
    "run_date",
    "run_type",
    "sequence",
    "event_kind",
    "phase",
    "operation",
    "document_key",
    "name",
    "status",
    "duration_ms",
    "retry_count",
    "sources",
    "input_summary",
    "output_summary",
    "created_at",
}
PRIVATE_ECONOMICS = {"prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd"}


@pytest.fixture(scope="module")
def statements() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def public_projection(statements: str) -> set[str]:
    match = re.search(
        r"CREATE OR REPLACE VIEW public\.olympus_run_event_trace.*?AS\s+SELECT(?P<body>.*?)"
        r"\s+FROM public\.olympus_run_events;",
        statements,
        re.I | re.S,
    )
    assert match, "missing curated olympus_run_event_trace view restatement"
    return {column.strip().lower() for column in match.group("body").split(",")}


@pytest.mark.unit
class TestNullableEconomics:
    @pytest.mark.parametrize("column", sorted(PRIVATE_ECONOMICS))
    def test_drops_not_null_default_zero(self, statements: str, column: str) -> None:
        assert re.search(
            rf"ALTER COLUMN {column}\s+DROP NOT NULL",
            statements,
            re.I,
        ), f"{column} must become nullable (append-only restatement)"
        assert re.search(
            rf"ALTER COLUMN {column}\s+DROP DEFAULT",
            statements,
            re.I,
        ), f"{column} must drop DEFAULT 0 so missing usage is not fabricated"

    @pytest.mark.parametrize("column", sorted(PRIVATE_ECONOMICS - {"cost_usd"}))
    def test_null_or_nonnegative_check(self, statements: str, column: str) -> None:
        assert re.search(
            rf"{column}\s+IS NULL OR {column}\s*>=\s*0",
            statements,
            re.I,
        ), f"{column} must allow NULL while rejecting negatives"


@pytest.mark.unit
class TestWp1JoinKeys:
    @pytest.mark.parametrize("column", sorted(JOIN_COLUMNS))
    def test_adds_uuid_join_column(self, statements: str, column: str) -> None:
        assert re.search(
            rf"ADD COLUMN IF NOT EXISTS {column}\s+uuid",
            statements,
            re.I,
        ), f"missing stamped WP1 join key {column}"

    def test_soft_stamp_not_hard_fk_to_attempts(self, statements: str) -> None:
        # Fail-soft quarantine on 067 means attempts may never land; a hard FK would
        # reject glass-box rows that should still persist for ordering honesty.
        assert not re.search(
            r"REFERENCES\s+public\.olympus_provider_attempts",
            statements,
            re.I,
        )


@pytest.mark.unit
class TestCuratedPublicView:
    def test_projects_join_keys_not_economics(self, public_projection: set[str]) -> None:
        assert public_projection == PUBLIC_BASE | JOIN_COLUMNS
        assert public_projection.isdisjoint(PRIVATE_ECONOMICS)

    def test_reaffirms_select_only_grants(self, statements: str) -> None:
        assert re.search(
            r"REVOKE ALL ON public\.olympus_run_event_trace FROM anon, authenticated",
            statements,
            re.I,
        )
        assert re.search(
            r"GRANT SELECT ON public\.olympus_run_event_trace TO anon, authenticated",
            statements,
            re.I,
        )
