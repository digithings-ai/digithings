"""Structural security checks for dashboard ordered call telemetry migration 066."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = REPO_ROOT / "digiquant" / "supabase" / "migrations" / "066_olympus_run_events.sql"
PUBLIC_COLUMNS = {
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
PRIVATE_COLUMNS = {"prompt_tokens", "completion_tokens", "cached_tokens", "cost_usd"}


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
    assert match, "missing curated olympus_run_event_trace view"
    return {column.strip().lower() for column in match.group("body").split(",")}


@pytest.mark.unit
class TestPrivateBaseTable:
    def test_enables_rls_without_public_policies(self, statements: str) -> None:
        assert "ALTER TABLE public.olympus_run_events ENABLE ROW LEVEL SECURITY" in statements
        assert not re.search(r"CREATE\s+POLICY", statements, re.I)

    def test_revokes_all_base_table_access(self, statements: str) -> None:
        assert re.search(
            r"REVOKE ALL ON public\.olympus_run_events FROM anon, authenticated",
            statements,
            re.I,
        )

    def test_primary_key_preserves_event_order_per_attempt(self, statements: str) -> None:
        assert re.search(r"PRIMARY KEY\s*\(run_id, attempt, sequence\)", statements, re.I)
        assert re.search(r"sequence\s+integer\s+NOT NULL CHECK \(sequence > 0\)", statements, re.I)


@pytest.mark.unit
class TestCuratedPublicView:
    def test_projects_only_approved_columns(self, public_projection: set[str]) -> None:
        assert public_projection == PUBLIC_COLUMNS
        assert public_projection.isdisjoint(PRIVATE_COLUMNS)

    def test_contains_no_body_or_credential_columns(self, public_projection: set[str]) -> None:
        joined = " ".join(public_projection)
        for forbidden in (
            "prompt",
            "argument",
            "result",
            "reasoning",
            "authorization",
            "credential",
            "secret",
            "bearer",
        ):
            assert forbidden not in joined

    def test_replaces_any_stale_grants_with_select_only(self, statements: str) -> None:
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


@pytest.mark.unit
class TestBoundedTelemetry:
    @pytest.mark.parametrize(
        ("column", "limit"),
        [
            ("run_id", 255),
            ("run_type", 100),
            ("phase", 120),
            ("operation", 200),
            ("document_key", 500),
            ("name", 255),
            ("input_summary", 500),
            ("output_summary", 500),
        ],
    )
    def test_public_text_column_has_length_check(
        self,
        statements: str,
        column: str,
        limit: int,
    ) -> None:
        assert re.search(
            rf"{column}\s+text[^\n]*char_length\({column}\) <= {limit}",
            statements,
            re.I,
        ), f"{column} is not bounded to {limit} characters"

    def test_event_enums_are_closed(self, statements: str) -> None:
        assert "event_kind IN ('model_call', 'search_call', 'tool_call')" in statements
        assert "status IN ('ok', 'error')" in statements
