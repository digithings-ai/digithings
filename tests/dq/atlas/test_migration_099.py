"""Contract tests for migration 099, the sealed broker credential store (K3).

Pure-SQL parse checks, mirroring `test_migration_069.py` — no database. What they pin is
the security shape a human reviewer of a credential table has to be able to trust at a
glance: RLS on with no policies, nothing granted to client roles, service_role reset before
its grant and then limited to SELECT/INSERT plus a **column-level** UPDATE on the three
lifecycle columns, every credential column immutable, no plaintext column anywhere, and the
structural guards (nonce length, ciphertext > tag, fingerprint shape) that make a
mis-encoded value fail here rather than as an unexplained authentication error later.

The two deliberate departures from 069 are asserted as such, so neither reads as an
oversight: 099 grants UPDATE (069 is append-only) because status/revoked_at/last_used_at
must change, and 099 does **not** trigger-block DELETE (069 does) because a credential
store must stay erasable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "099_broker_connections.sql"

TABLE = "broker_connections"
TRIGGER_FUNCTION = "reject_broker_connection_credential_mutation"
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")

# Columns service_role may change. Everything else on the row is credential or identity
# material and is immutable at the privilege layer.
UPDATABLE_COLUMNS = ("status", "revoked_at", "last_used_at")
IMMUTABLE_COLUMNS = (
    "id",
    "workspace_id",
    "broker",
    "env",
    "auth_kind",
    "ciphertext",
    "nonce",
    "key_id",
    "fingerprint",
    "scopes",
    "created_at",
)
# Column names that would mean a secret is stored in the clear. `key_id` is deliberately
# absent: in this table it names the master-key version, not a credential (the migration
# header and a COMMENT both say so).
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
    """Return the prose of a ``COMMENT ON <target> IS ...`` statement.

    A SQL string literal may contain ``;``, so the statement cannot be delimited by
    the next semicolon; match the run of concatenated literals and unquote it.
    """
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


# --- file shape -------------------------------------------------------------------


def test_migration_is_the_only_099(raw: str) -> None:
    assert sorted(MIGRATIONS_DIR.glob("099_*.sql")) == [MIGRATION_PATH]


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_header_records_the_number_coordination_and_the_human_gate(raw: str) -> None:
    """099 was taken by coordination with T0's 096-098 block, not by "next free", and the
    file has to say so — otherwise a later reader treats the gap as an accident and the
    renumber-at-merge instruction is lost."""
    header = raw[: raw.index("CREATE TABLE")]
    assert "HUMAN GATE" in header
    assert "096" in header and "098" in header
    assert "renumber" in header.lower()
    assert "test_migration_099.py" in header


# --- columns ----------------------------------------------------------------------


def test_primary_key_is_a_stable_uuid(table_body: str) -> None:
    assert re.search(r"\bid\s+uuid\s+PRIMARY KEY\s+DEFAULT\s+gen_random_uuid\(\)", table_body, re.I)


def test_workspace_id_is_required_and_references_workspaces(raw: str, table_body: str) -> None:
    """T0's 096 creates `workspaces` before 099 runs, so the FK belongs at CREATE time.

    T0's private-set backfill (097) deliberately skips `broker_connections` — K3 owns this
    column — so the reference must appear in this migration, not as a follow-up ALTER.
    """
    assert re.search(
        r"workspace_id\s+uuid\s+NOT NULL\s+REFERENCES\s+public\.workspaces\s*\(\s*id\s*\)",
        table_body,
        re.I,
    )
    assert "T0 will constrain" not in raw
    assert "FK-less" not in raw
    # Column COMMENT should also describe the live FK, not the pre-T0 placeholder.
    assert "FK to public.workspaces" in raw or "REFERENCES public.workspaces" in raw


@pytest.mark.parametrize(
    ("column", "values"),
    (
        ("broker", ("alpaca", "ibkr")),
        ("env", ("paper", "live")),
        ("auth_kind", ("oauth", "api_key")),
        ("status", ("active", "revoked", "expired")),
    ),
)
def test_state_columns_are_closed(table_body: str, column: str, values: tuple[str, ...]) -> None:
    match = re.search(rf"{column}\s+IN\s*\((?P<values>.*?)\)", table_body, re.I | re.S)
    assert match, f"missing closed CHECK for {TABLE}.{column}"
    assert set(re.findall(r"'([^']+)'", match.group("values"))) == set(values)


def test_nonce_length_is_pinned_to_96_bits(table_body: str) -> None:
    """A GCM nonce must be exactly 12 bytes; pinning it here turns a mis-encoded write
    into an immediate constraint violation instead of a later authentication failure."""
    assert re.search(
        r"nonce\s+bytea\s+NOT NULL\s+CHECK\s*\(\s*octet_length\(nonce\)\s*=\s*12\s*\)",
        table_body,
        re.I,
    )


def test_ciphertext_must_exceed_the_gcm_tag(table_body: str) -> None:
    """`> 16`, not `>= 16`: 16 bytes is the bare tag with no payload, i.e. truncated."""
    assert re.search(
        r"ciphertext\s+bytea\s+NOT NULL\s+CHECK\s*\(\s*octet_length\(ciphertext\)\s*>\s*16\s*\)",
        table_body,
        re.I,
    )


def test_fingerprint_is_pinned_to_eight_lowercase_hex(table_body: str) -> None:
    assert "fingerprint ~ '^[0-9a-f]{8}$'" in " ".join(table_body.split())


def test_key_id_shape_matches_the_python_key_id_pattern(table_body: str) -> None:
    """Same pattern the envelope's `_KEY_ID_PATTERN` enforces, so a value the runner
    accepts is a value the column accepts."""
    assert "key_id ~ '^[a-z0-9][a-z0-9._-]{0,31}$'" in " ".join(table_body.split())


def test_created_at_is_the_db_write_clock(table_body: str) -> None:
    assert re.search(r"created_at\s+timestamptz\s+NOT NULL\s+DEFAULT\s+now\(\)", table_body, re.I)


def test_one_active_connection_per_workspace_broker_env(table_body: str, sql: str) -> None:
    """Uniqueness is conditional on ``status = 'active'`` so revoke + insert can reconnect.

    An unconditional ``UNIQUE (workspace_id, broker, env)`` would collide once the old row
    is revoked (DELETE is not granted), contradicting the documented reconnect flow. A
    revoked row plus a new active row for the same triple must be able to coexist.
    """
    assert not re.search(
        r"CONSTRAINT\s+uq_broker_connections_workspace_broker_env", table_body, re.I
    )
    assert not re.search(
        r"UNIQUE\s*\(\s*workspace_id\s*,\s*broker\s*,\s*env\s*\)", table_body, re.I
    ), "table-level UNIQUE on the triple blocks revoke→reinsert"
    assert re.search(
        rf"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+uq_{TABLE}_active\s+"
        rf"ON\s+public\.{TABLE}\s*\(\s*workspace_id\s*,\s*broker\s*,\s*env\s*\)\s*"
        r"WHERE\s+status\s*=\s*'active'",
        sql,
        re.IGNORECASE,
    )
    # The unique partial index covers active-row lookup; a redundant non-unique twin must
    # not exist (it would be dead weight and invite drift with the unique predicate).
    assert not re.search(rf"idx_{TABLE}_active", sql, re.IGNORECASE)


def test_revoked_at_is_tied_to_the_revoked_status(table_body: str) -> None:
    normalized = " ".join(table_body.split())
    assert "status = 'revoked' AND revoked_at IS NOT NULL" in normalized
    assert "status <> 'revoked' AND revoked_at IS NULL" in normalized


def test_scopes_default_to_empty_and_admit_no_null_elements(table_body: str) -> None:
    normalized = " ".join(table_body.split())
    assert "scopes text[] NOT NULL DEFAULT '{}'" in normalized
    assert "array_position(scopes, NULL) IS NULL" in normalized


def test_no_plaintext_or_payload_column_exists(table_body: str) -> None:
    """The whole point of the table: the secret exists only inside `ciphertext`."""
    for forbidden in FORBIDDEN_COLUMNS:
        assert not re.search(rf"^\s*{forbidden}\s+", table_body, re.IGNORECASE | re.MULTILINE), (
            f"{TABLE} must not have a {forbidden!r} column"
        )


# --- privileges -------------------------------------------------------------------


def test_rls_is_enabled_with_no_policies(sql: str) -> None:
    assert re.search(rf"ALTER TABLE public\.{TABLE} ENABLE ROW LEVEL SECURITY;", sql, re.IGNORECASE)
    assert not re.search(rf"CREATE\s+POLICY[^;]*ON\s+public\.{TABLE}", sql, re.I | re.S)


def test_client_roles_are_fully_revoked(sql: str) -> None:
    revoke = re.search(rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+([^;]+);", sql, re.I)
    assert revoke, "missing client-role revoke"
    assert {role.strip() for role in revoke.group(1).split(",")} == set(PUBLIC_ROLES)


def test_no_privilege_is_granted_to_any_client_role(sql: str) -> None:
    for role in PUBLIC_ROLES:
        assert not re.search(
            rf"GRANT[^;]*ON\s+public\.{TABLE}\s+TO\s+[^;]*\b{role}\b", sql, re.I | re.S
        ), f"{TABLE} must grant nothing to {role}"


def test_service_role_is_reset_before_it_is_granted_anything(sql: str) -> None:
    """A Supabase project ships ALTER DEFAULT PRIVILEGES ... GRANT ALL TO service_role, so
    an additive grant alone would leave inherited UPDATE/DELETE/TRUNCATE in place."""
    revoke = re.search(rf"REVOKE\s+ALL\s+ON\s+public\.{TABLE}\s+FROM\s+service_role;", sql, re.I)
    grant = re.search(
        rf"GRANT\s+SELECT,\s*INSERT\s+ON\s+public\.{TABLE}\s+TO\s+service_role;", sql, re.I
    )
    assert revoke, "missing service_role reset"
    assert grant, "missing service_role SELECT/INSERT grant"
    assert revoke.end() < grant.start()


def test_service_role_gets_no_table_wide_update_or_delete(sql: str) -> None:
    grants = re.findall(
        rf"GRANT\s+(?P<privileges>[^;]+?)\s+ON\s+public\.{TABLE}\s+TO\s+service_role;", sql, re.I
    )
    assert grants
    for privileges in grants:
        normalized = " ".join(privileges.split()).upper()
        if "(" in normalized:  # the column-level UPDATE, asserted separately below
            continue
        assert set(normalized.split(", ")) == {"SELECT", "INSERT"}
    assert not re.search(rf"GRANT[^;(]*\bDELETE\b[^;]*ON\s+public\.{TABLE}", sql, re.I)
    assert not re.search(rf"GRANT[^;(]*\bTRUNCATE\b[^;]*ON\s+public\.{TABLE}", sql, re.I)
    assert not re.search(rf"GRANT\s+ALL[^;]*ON\s+public\.{TABLE}", sql, re.I)


def test_update_is_granted_column_level_on_the_lifecycle_columns_only(sql: str) -> None:
    """This is the primary immutability mechanism — a privilege, not a trigger. An UPDATE
    touching any credential column is refused before any trigger runs."""
    match = re.search(
        rf"GRANT\s+UPDATE\s*\((?P<columns>[^)]+)\)\s+ON\s+public\.{TABLE}\s+TO\s+service_role;",
        sql,
        re.IGNORECASE,
    )
    assert match, "missing column-level UPDATE grant"
    granted = {column.strip() for column in match.group("columns").split(",")}
    assert granted == set(UPDATABLE_COLUMNS)


# --- immutability triggers --------------------------------------------------------


def test_credential_columns_are_also_trigger_protected(sql: str) -> None:
    function = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{TRIGGER_FUNCTION}\(\).*?\$\$(?P<body>.*?)\$\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert function, f"missing {TRIGGER_FUNCTION}"
    body = " ".join(function.group("body").split())
    assert "RAISE EXCEPTION" in body.upper()
    for column in IMMUTABLE_COLUMNS:
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in body, (
            f"{column} is not covered by the immutability trigger"
        )
    for column in UPDATABLE_COLUMNS:
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" not in body, (
            f"{column} must remain updatable"
        )


def test_immutability_comparison_is_null_safe(sql: str) -> None:
    """`IS DISTINCT FROM`, never bare `<>`: `NULL <> NULL` is NULL, which an IF treats as
    false and would wave a nullable column's change straight through."""
    function = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{TRIGGER_FUNCTION}\(\).*?\$\$(?P<body>.*?)\$\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert function
    body = function.group("body")
    assert not re.search(r"NEW\.\w+\s*<>\s*OLD\.\w+", body)


def test_trigger_function_pins_its_search_path(sql: str) -> None:
    assert re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{TRIGGER_FUNCTION}\(\)\s+RETURNS trigger\s+"
        r"LANGUAGE plpgsql\s+SET search_path = ''",
        sql,
        re.IGNORECASE,
    )


def test_update_and_truncate_triggers_are_wired(sql: str) -> None:
    assert re.search(
        rf"CREATE TRIGGER reject_{TABLE}_credential_mutation\s+BEFORE UPDATE\s+"
        rf"ON public\.{TABLE}\s+FOR EACH ROW EXECUTE FUNCTION public\.{TRIGGER_FUNCTION}\(\)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        rf"CREATE TRIGGER reject_{TABLE}_truncate\s+BEFORE TRUNCATE\s+"
        rf"ON public\.{TABLE}\s+FOR EACH STATEMENT",
        sql,
        re.IGNORECASE | re.DOTALL,
    )


def test_triggers_are_replay_safe(sql: str) -> None:
    for trigger in (f"reject_{TABLE}_credential_mutation", f"reject_{TABLE}_truncate"):
        drop = sql.index(f"DROP TRIGGER IF EXISTS {trigger}")
        create = sql.index(f"CREATE TRIGGER {trigger}")
        assert drop < create


def test_delete_is_deliberately_not_trigger_blocked(raw: str, sql: str) -> None:
    """The departure from 069's append-only rule, asserted so it cannot be "fixed" by a
    later reader who assumes it was an omission: a credential store must stay erasable for
    workspace deletion and data-subject erasure. DELETE is simply never granted.
    """
    assert not re.search(r"BEFORE UPDATE OR DELETE", sql, re.IGNORECASE)
    assert "DELETE" not in re.search(
        r"CREATE TRIGGER reject_broker_connections_credential_mutation[^;]+;", sql, re.I
    ).group(0).upper().replace("DELETED", "")
    assert "erasable" in raw


def test_trigger_function_is_revoked_from_client_roles(sql: str) -> None:
    revoke = re.search(
        rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.{TRIGGER_FUNCTION}\(\)\s+FROM\s+([^;]+);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert revoke, "missing client-role revoke on the trigger function"
    assert {role.strip() for role in re.split(r",|\n", revoke.group(1)) if role.strip()} == set(
        PUBLIC_ROLES
    )


# --- documentation ----------------------------------------------------------------


def test_indexes_cover_workspace_lookup_and_the_active_row(sql: str) -> None:
    assert re.search(
        rf"CREATE INDEX IF NOT EXISTS idx_{TABLE}_workspace\s+ON public\.{TABLE} \(workspace_id\)",
        sql,
        re.IGNORECASE,
    )
    # Active-row uniqueness + lookup share one partial unique index (see
    # test_one_active_connection_per_workspace_broker_env).
    assert re.search(
        rf"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+uq_{TABLE}_active\s+"
        rf"ON\s+public\.{TABLE}\s*\(\s*workspace_id\s*,\s*broker\s*,\s*env\s*\)\s*"
        r"WHERE\s+status\s*=\s*'active'",
        sql,
        re.IGNORECASE,
    )


def test_key_id_comment_disambiguates_it_from_a_broker_key_id(sql: str) -> None:
    """The spec §3 sketch uses `key_id` for both the master-key version and a broker's own
    key identifier. Confusing them is how a reviewer concludes a secret is in the clear."""
    body = _comment_body(sql, rf"COLUMN\s+public\.{TABLE}\.key_id").lower()
    assert "master-key version" in body
    assert "not a" in body and "broker" in body


def test_table_comment_states_the_aad_binding_and_the_grant_shape(sql: str) -> None:
    body = _comment_body(sql, rf"TABLE\s+public\.{TABLE}")
    assert "workspace_id:broker:env" in body
    assert "revoke + insert" in body
    assert "active" in body.lower()
    assert "partial" in body.lower() or "coexist" in body.lower()
