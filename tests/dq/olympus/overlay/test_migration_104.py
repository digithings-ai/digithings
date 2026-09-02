"""Structural contract tests for migration 104 (BYOK LLM keys + job_runs status)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "104_workspace_provider_credentials.sql"

TABLE = "workspace_provider_credentials"
TRIGGER_FUNCTION = "reject_workspace_provider_credential_mutation"
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
UPDATABLE_COLUMNS = ("status", "revoked_at", "last_used_at")
IMMUTABLE_COLUMNS = (
    "id",
    "workspace_id",
    "provider",
    "auth_kind",
    "ciphertext",
    "nonce",
    "key_id",
    "fingerprint",
    "scopes",
    "created_at",
)
FORBIDDEN_COLUMNS = (
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "apikey",
    "password",
    "plaintext",
    "token",
    "credential",
    "credentials",
    "payload",
)
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
SQL_STRING = r"'(?:[^']|'')*'"


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def _comment_body(sql: str, target: str) -> str:
    match = re.search(
        rf"COMMENT\s+ON\s+{target}\s+IS\s+(?P<body>{SQL_STRING}(?:\s*{SQL_STRING})*)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing COMMENT ON {target}"
    literals = re.findall(SQL_STRING, match.group("body"), re.DOTALL)
    return " ".join("".join(text[1:-1].replace("''", "'") for text in literals).split())


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


@pytest.fixture(scope="module")
def table_body(sql: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{TABLE}\s*\((?P<body>.*?)\n\);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {TABLE}"
    return match.group("body")


def test_migration_is_the_only_104() -> None:
    assert sorted(MIGRATIONS_DIR.glob("104_*.sql")) == [MIGRATION_PATH]


def test_header_reuses_k3_envelope_and_aad(raw: str) -> None:
    header = raw[: raw.index("CREATE TABLE")]
    assert "HUMAN GATE" in header
    assert "workspace_id:provider:llm" in raw
    assert "digiquant.vault.envelope" in header
    assert "job_runs" in header
    assert "skipped" in header
    assert "budget_exhausted" in header


def test_job_runs_status_extended(sql: str) -> None:
    assert re.search(
        r"ALTER TABLE public\.job_runs DROP CONSTRAINT IF EXISTS job_runs_status_check",
        sql,
        re.I,
    )
    match = re.search(
        r"ALTER TABLE public\.job_runs ADD CONSTRAINT job_runs_status_check\s+"
        r"CHECK \(status IN \((?P<values>.*?)\)\)",
        sql,
        re.I | re.S,
    )
    assert match
    values = set(re.findall(r"'([^']+)'", match.group("values")))
    assert values == {
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "budget_exhausted",
    }


def test_workspace_id_fk_to_workspaces(table_body: str) -> None:
    assert re.search(
        r"workspace_id\s+uuid\s+NOT NULL\s+REFERENCES public\.workspaces",
        table_body,
        re.I,
    )


def test_provider_vocabulary(table_body: str) -> None:
    match = re.search(r"provider\s+IN\s*\((?P<values>.*?)\)", table_body, re.I | re.S)
    assert match
    assert set(re.findall(r"'([^']+)'", match.group("values"))) == {
        "openai",
        "anthropic",
        "groq",
        "openrouter",
        "xai",
        "gemini",
    }


def test_envelope_shape_mirrors_099(table_body: str) -> None:
    assert re.search(
        r"nonce\s+bytea\s+NOT NULL\s+CHECK\s*\(\s*octet_length\(nonce\)\s*=\s*12", table_body, re.I
    )
    assert re.search(
        r"ciphertext\s+bytea\s+NOT NULL\s+CHECK\s*\(\s*octet_length\(ciphertext\)\s*>\s*16",
        table_body,
        re.I,
    )
    assert "fingerprint ~ '^[0-9a-f]{8}$'" in " ".join(table_body.split())


def test_partial_unique_active(sql: str) -> None:
    assert re.search(
        rf"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+uq_{TABLE}_active\s+"
        rf"ON\s+public\.{TABLE}\s*\(\s*workspace_id\s*,\s*provider\s*\)\s*"
        r"WHERE\s+status\s*=\s*'active'",
        sql,
        re.IGNORECASE,
    )


def test_rls_none_column_grant(sql: str) -> None:
    assert re.search(rf"ALTER TABLE public\.{TABLE} ENABLE ROW LEVEL SECURITY;", sql, re.I)
    assert not re.search(rf"CREATE\s+POLICY[^;]*ON\s+public\.{TABLE}", sql, re.I | re.S)
    revoke = re.search(rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+([^;]+);", sql, re.I)
    assert revoke
    assert {role.strip() for role in revoke.group(1).split(",")} == set(PUBLIC_ROLES)
    match = re.search(
        rf"GRANT\s+UPDATE\s*\((?P<columns>[^)]+)\)\s+ON\s+public\.{TABLE}\s+TO\s+service_role;",
        sql,
        re.I,
    )
    assert match
    assert {c.strip() for c in match.group("columns").split(",")} == set(UPDATABLE_COLUMNS)


def test_immutability_trigger(sql: str) -> None:
    function = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{TRIGGER_FUNCTION}\(\).*?\$\$(?P<body>.*?)\$\$;",
        sql,
        re.I | re.S,
    )
    assert function
    body = " ".join(function.group("body").split())
    for column in IMMUTABLE_COLUMNS:
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in body
    for column in UPDATABLE_COLUMNS:
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" not in body


def test_no_plaintext_column(table_body: str) -> None:
    for forbidden in FORBIDDEN_COLUMNS:
        assert not re.search(rf"^\s*{forbidden}\s+", table_body, re.I | re.M)


def test_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_table_comment_states_aad(sql: str) -> None:
    body = _comment_body(sql, rf"TABLE\s+public\.{TABLE}")
    assert "workspace_id:provider:llm" in body
    assert "K3" in body or "envelope" in body.lower()
