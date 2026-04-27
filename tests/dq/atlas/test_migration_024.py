"""Unit tests for migration 024 (thesis + deliberation first-class tables).

These tests are deliberately hermetic: they parse the migration SQL file and
assert structural properties (CREATE TABLE presence, PKs / FKs / CHECK
clauses, RLS enablement, per-table anon SELECT policy, rollback block).

They do NOT spin up Postgres. A live round-trip test (`psycopg` against a
throwaway DB) belongs in a separate integration test once Wave 2 lands the
Python adapters — see ADR-0010. Keeping this suite pure-SQL avoids marking a
new `integration` pytest marker (the project registers only `unit` and
`e2e`) and lets `make test-unit` stay offline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "apps"
    / "digiquant-atlas"
    / "supabase"
    / "migrations"
    / "024_thesis_deliberation_first_class.sql"
)

EXPECTED_TABLES = (
    "thesis_vehicles",
    "deliberation_sessions",
    "deliberation_rounds",
    "analyst_coverage",
    "deep_dive_triggers",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    """Strip SQL line comments so assertions don't match rollback-block text."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _table_block(sql: str, table: str) -> str:
    """Extract the `CREATE TABLE ... );` block for a single table.

    Scopes per-table column / constraint assertions so a column that exists
    on a later table does not satisfy a check for an earlier one. Returns the
    block including the closing paren of the CREATE TABLE statement plus any
    immediately-following CREATE INDEX / ALTER TABLE / CREATE POLICY lines up
    to the next `CREATE TABLE` or end-of-file.
    """
    body = _strip_comments(sql)
    start = re.search(rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", body)
    assert start, f"CREATE TABLE for {table} not found"
    next_tbl = re.search(r"CREATE TABLE IF NOT EXISTS\s+\w+", body[start.end() :])
    end = start.end() + next_tbl.start() if next_tbl else len(body)
    return body[start.start() : end]


@pytest.mark.unit
class TestMigrationFilePresent:
    def test_file_exists_and_nonempty(self, sql: str) -> None:
        assert len(sql) > 500, "migration file looks truncated"

    def test_begin_commit_wraps_body(self, sql: str) -> None:
        body = _strip_comments(sql)
        assert body.count("BEGIN;") >= 1
        assert body.count("COMMIT;") >= 1

    def test_rollback_block_present_but_commented(self, sql: str) -> None:
        """Rollback DROP TABLEs must be commented so re-running the migration
        does not drop the tables it just created.

        DROP POLICY IF EXISTS is allowed uncommented — existing Atlas
        migrations (005/007/015/023) use it for idempotent policy replace.
        """
        assert "Rollback" in sql, "no rollback section header"
        for idx, line in enumerate(sql.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("DROP TABLE"):
                pytest.fail(f"line {idx}: uncommented DROP TABLE in migration: {stripped!r}")


@pytest.mark.unit
class TestExpectedTablesCreated:
    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_create_table(self, sql: str, table: str) -> None:
        body = _strip_comments(sql)
        assert re.search(rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", body), (
            f"missing CREATE TABLE for {table}"
        )

    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_rls_enabled(self, sql: str, table: str) -> None:
        body = _strip_comments(sql)
        assert re.search(rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY", body), (
            f"RLS not enabled on {table}"
        )

    @pytest.mark.parametrize("table", EXPECTED_TABLES)
    def test_anon_select_policy(self, sql: str, table: str) -> None:
        body = _strip_comments(sql)
        # Policy name matches the convention used by migrations 005/007/015/023.
        assert re.search(
            rf'CREATE POLICY\s+"{table}_anon_select"\s+ON\s+{table}\s+FOR SELECT\s+TO anon',
            body,
        ), f"anon select policy missing on {table}"


@pytest.mark.unit
class TestThesisVehiclesShape:
    def test_composite_pk(self, sql: str) -> None:
        block = _table_block(sql, "thesis_vehicles")
        assert re.search(r"PRIMARY KEY\s*\(\s*date\s*,\s*thesis_id\s*,\s*ticker\s*\)", block)

    def test_fk_to_theses(self, sql: str) -> None:
        block = _table_block(sql, "thesis_vehicles")
        assert re.search(
            r"FOREIGN KEY\s*\(\s*date\s*,\s*thesis_id\s*\)"
            r"\s*REFERENCES\s+theses\s*\(\s*date\s*,\s*thesis_id\s*\)",
            block,
        )

    @pytest.mark.parametrize(
        "col",
        [
            "rationale",
            "exclusion_reasons",
            "candidate_rank",
            "user_mandate_notes",
            "source_exploration_key",
            "created_at",
        ],
    )
    def test_expected_columns(self, sql: str, col: str) -> None:
        block = _table_block(sql, "thesis_vehicles")
        assert re.search(rf"\b{col}\b", block), f"thesis_vehicles missing {col}"


@pytest.mark.unit
class TestDeliberationSessionsShape:
    def test_primary_key_uuid(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_sessions")
        assert re.search(r"session_id\s+uuid\s+PRIMARY KEY", block)

    def test_kind_check_constraint(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_sessions")
        assert re.search(
            r"kind IN\s*\(\s*'baseline'\s*,\s*'delta_scoped'\s*,\s*'monthly'\s*\)",
            block,
        )

    def test_unique_triple(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_sessions")
        assert re.search(r"UNIQUE\s*\(\s*date\s*,\s*kind\s*,\s*pipeline_run_id\s*\)", block)


@pytest.mark.unit
class TestDeliberationRoundsShape:
    def test_fk_to_sessions(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_rounds")
        assert re.search(r"REFERENCES\s+deliberation_sessions\s*\(\s*session_id\s*\)", block)

    def test_unique_triple(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_rounds")
        assert re.search(
            r"UNIQUE\s*\(\s*session_id\s*,\s*ticker\s*,\s*round_number\s*\)",
            block,
        )

    def test_indexed_on_ticker_session(self, sql: str) -> None:
        block = _table_block(sql, "deliberation_rounds")
        assert re.search(
            r"CREATE INDEX[\s\S]*?ON\s+deliberation_rounds\s*\(\s*ticker\s*,\s*session_id\s*\)",
            block,
        )

    @pytest.mark.parametrize(
        "col", ["converged", "recess_triggered", "deep_dive_document_key", "sections"]
    )
    def test_expected_columns(self, sql: str, col: str) -> None:
        block = _table_block(sql, "deliberation_rounds")
        assert re.search(rf"\b{col}\b", block), f"deliberation_rounds missing {col}"


@pytest.mark.unit
class TestAnalystCoverageShape:
    def test_composite_pk(self, sql: str) -> None:
        block = _table_block(sql, "analyst_coverage")
        assert re.search(r"PRIMARY KEY\s*\(\s*date\s*,\s*ticker\s*\)", block)

    @pytest.mark.parametrize(
        "col",
        ["thesis_ids", "analyst_role", "current_recommendation_key", "last_updated"],
    )
    def test_expected_columns(self, sql: str, col: str) -> None:
        block = _table_block(sql, "analyst_coverage")
        assert re.search(rf"\b{col}\b", block), f"analyst_coverage missing {col}"


@pytest.mark.unit
class TestDeepDiveTriggersShape:
    def test_triggered_by_check(self, sql: str) -> None:
        block = _table_block(sql, "deep_dive_triggers")
        assert re.search(
            r"triggered_by IN\s*\(\s*'pm_recess'\s*,\s*'delta_watch'\s*,\s*'manual'\s*\)",
            block,
        )

    def test_session_fk_nullable(self, sql: str) -> None:
        """session_id may be NULL (manual triggers without a session)."""
        block = _table_block(sql, "deep_dive_triggers")
        assert re.search(
            r"session_id\s+uuid\b(?![^\n]*NOT NULL)[\s\S]*?REFERENCES\s+deliberation_sessions",
            block,
        ), "deep_dive_triggers.session_id should be nullable FK"

    @pytest.mark.parametrize(
        "col", ["ticker", "trigger_reason", "deep_dive_document_key", "resolved_at"]
    )
    def test_expected_columns(self, sql: str, col: str) -> None:
        block = _table_block(sql, "deep_dive_triggers")
        assert re.search(rf"\b{col}\b", block), f"deep_dive_triggers missing {col}"


@pytest.mark.unit
class TestMigrationNumbering:
    def test_no_duplicate_number(self) -> None:
        migrations_dir = MIGRATION_PATH.parent
        prefixes = [p.name.split("_", 1)[0] for p in migrations_dir.glob("*.sql")]
        # 024 must appear exactly once.
        assert prefixes.count("024") == 1

    def test_file_prefix_is_024(self) -> None:
        assert MIGRATION_PATH.name.startswith("024_")
