"""Contract tests for migration 067, the private provider telemetry ledger."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "067_olympus_provider_telemetry.sql"

TABLES = (
    "olympus_node_runs",
    "olympus_provider_calls",
    "olympus_provider_attempts",
)
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
FORBIDDEN_COLUMNS = (
    "prompt",
    "prompt_body",
    "prompt_content",
    "response",
    "response_body",
    "response_content",
    "message",
    "messages",
    "api_key",
    "secret",
    "raw_exception",
    "search_text",
    # The fan-out discriminator is stored as the deliberately generic `fanout_key`. These names
    # would mean the dashboard vocabulary leaked into the shared ledger.
    "ticker",
    "symbol",
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


def test_migration_is_the_only_067() -> None:
    assert sorted(MIGRATIONS_DIR.glob("067_*.sql")) == [MIGRATION_PATH]


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_use_stable_uuid_primary_keys(sql: str, table: str) -> None:
    body = _table_body(sql, table)
    expected_id = {
        "olympus_node_runs": "node_run_id",
        "olympus_provider_calls": "call_id",
        "olympus_provider_attempts": "attempt_id",
    }[table]
    assert re.search(rf"\b{expected_id}\s+uuid\s+PRIMARY KEY\b", body, re.IGNORECASE)


def test_node_run_fanout_key_is_nullable(sql: str) -> None:
    """A node with no fan-out cursor has no key — absent, never a fabricated placeholder."""
    body = _table_body(sql, "olympus_node_runs")
    definition = re.search(r"\bfanout_key\s+text(?P<tail>[^,\n]*)", body, re.IGNORECASE)
    assert definition, "missing fanout_key"
    assert "NOT NULL" not in definition.group("tail").upper()
    assert "DEFAULT" not in definition.group("tail").upper()


def test_node_run_fanout_key_is_length_bounded(sql: str) -> None:
    """Same literal bound as NodeRunRecord.fanout_key (asserted cross-layer below)."""
    body = " ".join(_table_body(sql, "olympus_node_runs").split())
    assert "fanout_key IS NULL OR length(fanout_key) BETWEEN 1 AND 200" in body


def test_python_sql_string_and_nonnegative_bounds_agree(sql: str) -> None:
    """Keep 067 CHECKs and digillm Field constraints in lockstep (#1989).

    Append-only tables cannot correct a row that Pydantic accepted and Postgres rejected.
    This is the cheap gate that replaces hand enumeration of ~30 pairs.
    """
    from typing import get_args

    from digillm.telemetry import NodeRunRecord, ProviderAttemptRecord, ProviderCallRecord

    def _constraint_items(model: type, field: str) -> list[object]:
        meta = model.model_fields[field]
        items: list[object] = list(meta.metadata)
        for arg in get_args(meta.annotation):
            for annotated_meta in getattr(arg, "__metadata__", ()):
                nested = getattr(annotated_meta, "metadata", None)
                if nested is not None:
                    items.extend(nested)
                else:
                    items.append(annotated_meta)
        return items

    def max_len(model: type, field: str) -> int:
        for item in _constraint_items(model, field):
            bound = getattr(item, "max_length", None)
            if bound is not None:
                return int(bound)
        raise AssertionError(f"{model.__name__}.{field} missing max_length metadata")

    def has_ge0(model: type, field: str) -> bool:
        return any(getattr(item, "ge", None) == 0 for item in _constraint_items(model, field))

    node_body = " ".join(_table_body(sql, "olympus_node_runs").split())
    call_body = " ".join(_table_body(sql, "olympus_provider_calls").split())
    attempt_body = " ".join(_table_body(sql, "olympus_provider_attempts").split())

    fanout = max_len(NodeRunRecord, "fanout_key")
    assert f"length(fanout_key) BETWEEN 1 AND {fanout}" in node_body

    for body, model in (
        (call_body, ProviderCallRecord),
        (attempt_body, ProviderAttemptRecord),
    ):
        model_len = max_len(model, "requested_model")
        err_len = max_len(model, "error_type")
        assert f"length(requested_model) BETWEEN 1 AND {model_len}" in body
        assert f"length(error_type) BETWEEN 1 AND {err_len}" in body

    assert has_ge0(ProviderCallRecord, "attempt_count")
    assert "attempt_count >= 0" in call_body
    assert has_ge0(ProviderAttemptRecord, "prompt_tokens")
    assert has_ge0(ProviderAttemptRecord, "completion_tokens")
    assert "prompt_tokens IS NULL OR prompt_tokens >= 0" in attempt_body
    assert "completion_tokens IS NULL OR completion_tokens >= 0" in attempt_body
    assert has_ge0(ProviderAttemptRecord, "cost_usd")
    assert "cost_usd IS NULL OR cost_usd >= 0" in attempt_body


def test_calls_require_node_parent_and_support_logical_parent(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_calls")
    assert re.search(r"node_run_id\s+uuid\s+NOT NULL", body, re.IGNORECASE)
    assert re.search(
        r"FOREIGN KEY\s*\(node_run_id\)\s+REFERENCES\s+public\.olympus_node_runs",
        body,
        re.IGNORECASE,
    )
    assert re.search(r"parent_call_id\s+uuid", body, re.IGNORECASE)
    assert re.search(
        r"FOREIGN KEY\s*\(parent_call_id\)\s+REFERENCES\s+public\.olympus_provider_calls",
        body,
        re.IGNORECASE,
    )


def test_attempts_require_call_parent_and_unique_sequence(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_attempts")
    assert re.search(r"call_id\s+uuid\s+NOT NULL", body, re.IGNORECASE)
    assert re.search(
        r"FOREIGN KEY\s*\(call_id\)\s+REFERENCES\s+public\.olympus_provider_calls",
        body,
        re.IGNORECASE,
    )
    assert re.search(r"UNIQUE\s*\(call_id,\s*attempt_number\)", body, re.IGNORECASE)
    assert re.search(r"CHECK\s*\(attempt_number\s*>\s*0\)", body, re.IGNORECASE)


@pytest.mark.parametrize("table", TABLES)
def test_event_and_recorded_times_are_timezone_aware(sql: str, table: str) -> None:
    body = _table_body(sql, table)
    assert re.search(r"started_at\s+timestamptz\s+NOT NULL", body, re.IGNORECASE)
    assert re.search(r"finished_at\s+timestamptz", body, re.IGNORECASE)
    assert re.search(
        r"recorded_at\s+timestamptz\s+NOT NULL\s+DEFAULT\s+now\(\)",
        body,
        re.IGNORECASE,
    )


def test_missing_attempt_usage_and_cost_are_nullable(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_attempts")
    for column, data_type in (
        ("prompt_tokens", "bigint"),
        ("completion_tokens", "bigint"),
        ("cost_usd", "numeric"),
    ):
        definition = re.search(rf"\b{column}\s+{data_type}(?P<tail>[^,\n]*)", body, re.IGNORECASE)
        assert definition, f"missing {column}"
        assert "NOT NULL" not in definition.group("tail").upper()
        assert "DEFAULT" not in definition.group("tail").upper()


def test_cache_hit_can_have_zero_attempts_but_other_success_cannot(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_calls")
    normalized = " ".join(body.split())
    assert "attempt_count >= 0" in normalized
    assert "cache_status = 'hit' AND attempt_count = 0" in normalized
    assert "outcome <> 'succeeded' OR attempt_count > 0" in normalized


def test_calls_require_exactly_one_artifact_disposition(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_calls")
    normalized = " ".join(body.split())
    assert "jsonb_array_length(artifacts) > 0 AND no_artifact_reason IS NULL" in normalized
    assert "jsonb_array_length(artifacts) = 0 AND no_artifact_reason IS NOT NULL" in normalized


def test_failed_calls_require_sanitized_error_type(sql: str) -> None:
    body = _table_body(sql, "olympus_provider_calls")
    normalized = " ".join(body.split())
    assert "outcome = 'failed' AND error_type IS NOT NULL" in normalized
    assert "outcome <> 'failed' AND error_type IS NULL" in normalized


def test_terminal_calls_require_matching_artifact_disposition(sql: str) -> None:
    """The terminal-disposition CHECK must be NULL-safe.

    Postgres admits a CHECK that evaluates to NULL, so plain ``=`` against a NULL
    ``no_artifact_reason`` accepts ``(failed, NULL, artifacts)`` and ``(cancelled, NULL,
    artifacts)`` — rows the Pydantic producer rejects, and which the append-only triggers
    then make permanent. ``IS NOT DISTINCT FROM`` is the discriminating detail.
    """
    body = _table_body(sql, "olympus_provider_calls")
    normalized = " ".join(body.split())
    assert (
        "outcome = 'failed' AND no_artifact_reason IS NOT DISTINCT FROM 'call_failed'"
    ) in normalized
    assert (
        "outcome = 'cancelled' AND no_artifact_reason IS NOT DISTINCT FROM 'call_cancelled'"
    ) in normalized
    assert "outcome IN ('started', 'succeeded')" in normalized
    assert "no_artifact_reason = 'call_failed'" not in normalized
    assert "no_artifact_reason = 'call_cancelled'" not in normalized


@pytest.mark.parametrize("table", ("olympus_provider_calls", "olympus_provider_attempts"))
def test_provider_identifiers_have_length_bounds(sql: str, table: str) -> None:
    body = " ".join(_table_body(sql, table).split())
    assert "length(requested_model) BETWEEN 1 AND 256" in body
    assert "error_type IS NULL OR length(error_type) BETWEEN 1 AND 200" in body


@pytest.mark.parametrize(
    ("table", "column", "values"),
    (
        ("olympus_node_runs", "outcome", ("started", "succeeded", "failed", "cancelled")),
        (
            "olympus_provider_calls",
            "purpose",
            (
                "initial_generation",
                "chat_completion",
                "structured_completion",
                "structured_repair",
                "tool_selection",
                "tool_follow_up",
                "web_grounding",
                "x_grounding",
                "tool_loop",
                "web_search",
                "x_search",
                "embedding",
            ),
        ),
        (
            "olympus_provider_calls",
            "cache_status",
            ("bypassed", "hit", "miss", "unavailable"),
        ),
        (
            "olympus_provider_calls",
            "no_artifact_reason",
            (
                "consumed_inline",
                "tool_dispatch",
                "validation_rejected",
                "no_output",
                "call_failed",
                "call_cancelled",
                "unknown",
            ),
        ),
        (
            "olympus_provider_attempts",
            "retry_reason",
            (
                "not_applicable",
                "rate_limit",
                "timeout",
                "connection_error",
                "empty_response",
                "server_error",
                "unknown",
            ),
        ),
    ),
)
def test_state_columns_are_closed(
    sql: str, table: str, column: str, values: tuple[str, ...]
) -> None:
    body = _table_body(sql, table)
    match = re.search(rf"CHECK\s*\(\s*{column}\s+IN\s*\((?P<values>.*?)\)\s*\)", body, re.I | re.S)
    assert match, f"missing closed CHECK for {table}.{column}"
    assert set(re.findall(r"'([^']+)'", match.group("values"))) == set(values)


def test_schema_has_no_payload_or_secret_columns(sql: str) -> None:
    bodies = "\n".join(_table_body(sql, table) for table in TABLES)
    for forbidden in FORBIDDEN_COLUMNS:
        assert not re.search(
            rf"^\s*{forbidden}\s+",
            bodies,
            re.IGNORECASE | re.MULTILINE,
        )


@pytest.mark.parametrize("table", TABLES)
def test_tables_are_private(sql: str, table: str) -> None:
    assert re.search(
        rf"ALTER TABLE public\.{table} ENABLE ROW LEVEL SECURITY;",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(rf"CREATE\s+POLICY[^;]*ON\s+public\.{table}", sql, re.I | re.S)
    revoke = re.search(rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+([^;]+);", sql, re.I)
    assert revoke, f"missing complete client revoke for {table}"
    revoked_roles = {role.strip() for role in revoke.group(1).split(",")}
    assert revoked_roles == set(PUBLIC_ROLES)


@pytest.mark.parametrize("table", TABLES)
def test_service_role_can_only_insert_and_read(sql: str, table: str) -> None:
    revoke = re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+service_role;",
        sql,
        re.IGNORECASE,
    )
    grant = re.search(
        rf"GRANT\s+(?P<privileges>[^;]+?)\s+ON\s+public\.{table}\s+TO\s+service_role;",
        sql,
        re.IGNORECASE,
    )
    assert revoke, f"missing service_role reset for {table}"
    assert grant, f"missing service_role grant for {table}"
    assert revoke.end() < grant.start(), (
        f"service_role privileges are not reset before {table} grant"
    )
    privileges = {item.strip().upper() for item in grant.group("privileges").split(",")}
    assert privileges == {"SELECT", "INSERT"}


@pytest.mark.parametrize("table", TABLES)
def test_mutation_rejection_trigger_guards_each_table(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE TRIGGER reject_{table}_mutation\s+BEFORE UPDATE OR DELETE\s+"
        rf"ON public\.{table}",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        rf"CREATE TRIGGER reject_{table}_truncate\s+BEFORE TRUNCATE\s+"
        rf"ON public\.{table}\s+FOR EACH STATEMENT",
        sql,
        re.IGNORECASE | re.DOTALL,
    )


def test_mutation_trigger_always_raises(sql: str) -> None:
    function = re.search(
        r"CREATE OR REPLACE FUNCTION public\.reject_olympus_provider_telemetry_mutation\(\)"
        r".*?\$\$(?P<body>.*?)\$\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert function
    assert "RAISE EXCEPTION" in function.group("body").upper()
