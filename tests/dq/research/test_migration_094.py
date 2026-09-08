"""Contract tests for migration 094, private policy replay governance store (#2983 / WP16.2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "094_olympus_policy_replay.sql"

TABLES = (
    "olympus_replay_input_manifests",
    "olympus_replay_pairs",
    "olympus_replay_run_events",
    "olympus_replay_arm_results",
    "olympus_policy_comparison_reports",
    "olympus_gate_criteria_versions",
    "olympus_gate_evaluations",
    "olympus_policy_governance_decisions",
)
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


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {table}"
    return match.group("body")


def test_migration_is_the_only_094() -> None:
    assert sorted(MIGRATIONS_DIR.glob("094_*.sql")) == [MIGRATION_PATH]


def test_migration_follows_093() -> None:
    assert (MIGRATIONS_DIR / "093_olympus_outcome_learning.sql").is_file()


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_historical_backfill(sql: str) -> None:
    assert "INSERT INTO" not in sql.upper()


def test_no_public_view(sql: str) -> None:
    assert "CREATE VIEW" not in sql.upper()
    assert "CREATE OR REPLACE VIEW" not in sql.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_exist(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
        sql,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_privacy_rls_and_grants(sql: str, table: str) -> None:
    assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert f"REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated" in sql
    assert f"REVOKE ALL ON public.{table} FROM service_role" in sql
    assert f"GRANT SELECT, INSERT ON public.{table} TO service_role" in sql


@pytest.mark.parametrize("table", TABLES)
def test_append_only_triggers(sql: str, table: str) -> None:
    assert "reject_olympus_policy_replay_mutation" in sql
    assert f"BEFORE UPDATE OR DELETE ON public.{table}" in sql
    assert f"BEFORE TRUNCATE ON public.{table}" in sql


def test_manifest_content_hash_unique(sql: str) -> None:
    body = _table_body(sql, "olympus_replay_input_manifests")
    assert "UNIQUE (manifest_content_hash)" in body.replace("\n", " ")


def test_pair_manifest_fk(sql: str) -> None:
    body = _table_body(sql, "olympus_replay_pairs")
    assert re.search(
        r"FOREIGN KEY\s*\(shared_manifest_content_hash\)\s+REFERENCES\s+"
        r"public\.olympus_replay_input_manifests",
        body,
        re.I,
    )


def test_run_events_unique_sequence(sql: str) -> None:
    body = _table_body(sql, "olympus_replay_run_events")
    assert "UNIQUE (run_id, sequence)" in body.replace("\n", " ")


def test_arm_results_unique_run_arm(sql: str) -> None:
    body = _table_body(sql, "olympus_replay_arm_results")
    assert "UNIQUE (run_id, arm_id)" in body.replace("\n", " ")


def test_criteria_supersedes_fk(sql: str) -> None:
    body = _table_body(sql, "olympus_gate_criteria_versions")
    assert re.search(
        r"FOREIGN KEY\s*\(supersedes_version_id\)\s+REFERENCES\s+"
        r"public\.olympus_gate_criteria_versions",
        body,
        re.I,
    )


def test_evaluation_fks(sql: str) -> None:
    body = _table_body(sql, "olympus_gate_evaluations")
    assert "REFERENCES public.olympus_policy_comparison_reports" in body.replace("\n", " ")
    assert "REFERENCES public.olympus_gate_criteria_versions" in body.replace("\n", " ")


def test_decision_supersedes_fk(sql: str) -> None:
    body = _table_body(sql, "olympus_policy_governance_decisions")
    assert re.search(
        r"FOREIGN KEY\s*\(supersedes_decision_id\)\s+REFERENCES\s+"
        r"public\.olympus_policy_governance_decisions",
        body,
        re.I,
    )
