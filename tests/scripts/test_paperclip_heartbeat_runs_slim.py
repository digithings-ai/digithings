"""Tests for scripts/paperclip_heartbeat_runs_slim.py.

The cleanup must write the same shape as the paperclip write-time trigger
(digithings-ai/paperclip@1c918d30b, migration 0308). These tests pin that
shape: the trigger keeps every key of the snapshot and replaces the body of
every comment of the top-level continuation with a SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "paperclip_heartbeat_runs_slim.py"
_GUARD = _REPO_ROOT / "scripts" / "check_plaintext_credentials.py"

# The digest the database computes for the body "hello":
#   encode(sha256(convert_to('hello', 'UTF8')), 'hex')
# It is measured on the database, so a change of encoding in either language
# shows up here instead of on the next write.
HELLO_DIGEST = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "paperclip_heartbeat_runs_slim", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load()


def _args(**overrides):
    import argparse

    values = {
        "dsn": "",
        "host": "127.0.0.1",
        "port": 54329,
        "user": "paperclip",
        "dbname": "paperclip",
        "password_env": "PGPASSWORD",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _snapshot() -> dict:
    """A snapshot with every shape the transform has to decide about."""
    return {
        "issueId": "issue-1",
        "taskId": "task-1",
        "paperclipTaskMarkdown": "# the rendered prompt",
        "paperclipTaskMarkdownCompact": "# the rendered prompt, compact",
        "paperclipFreshSessionHandoffMarkdown": "# the handoff",
        "paperclipWake": {
            "issue": {"id": "issue-1", "workMode": "standard", "title": "a title"},
            "comments": [{"id": "c1", "body": "the wake comment"}],
            "continuationSummary": {"count": 1},
            "executionContinuation": {"messages": [{"message": {"body": "inner"}}]},
        },
        "executionContinuation": {
            "originCommentIds": ["c1"],
            "messages": [
                {"id": "m1", "author": "agent", "body": "the body of the first message"},
                {"id": "m2", "author": "user", "body": "the body of the second message"},
            ],
        },
    }


# --------------------------------------------------------------------------
# The Python reference: the readable copy of the trigger's shape
# --------------------------------------------------------------------------


def test_the_reference_keeps_every_key_of_the_snapshot(script):
    slim = script.slim_snapshot(_snapshot())
    assert slim["paperclipTaskMarkdown"] == "# the rendered prompt"
    assert slim["paperclipTaskMarkdownCompact"] == "# the rendered prompt, compact"
    assert slim["paperclipFreshSessionHandoffMarkdown"] == "# the handoff"
    assert slim["issueId"] == "issue-1"
    assert slim["taskId"] == "task-1"
    wake = slim["paperclipWake"]
    assert wake["issue"] == {"id": "issue-1", "workMode": "standard", "title": "a title"}
    assert wake["comments"] == [{"id": "c1", "body": "the wake comment"}]
    assert wake["continuationSummary"] == {"count": 1}
    assert wake["executionContinuation"] == {"messages": [{"message": {"body": "inner"}}]}


def test_the_reference_digests_the_continuation_bodies(script):
    slim = script.slim_snapshot(_snapshot())
    messages = slim["executionContinuation"]["messages"]
    assert [message["id"] for message in messages] == ["m1", "m2"]
    for message in messages:
        assert "body" not in message
        assert message["author"] in {"agent", "user"}
    expected = hashlib.sha256("the body of the first message".encode("utf-8")).hexdigest()
    assert messages[0]["bodyDigest"] == expected


def test_the_reference_keeps_the_rest_of_the_continuation(script):
    slim = script.slim_snapshot(_snapshot())
    assert slim["executionContinuation"]["originCommentIds"] == ["c1"]


def test_the_reference_leaves_a_message_without_a_string_body_alone(script):
    snapshot = {"executionContinuation": {"messages": [{"id": "m1", "body": 42}, "text"]}}
    assert script.slim_snapshot(snapshot) == snapshot


def test_the_reference_leaves_a_snapshot_without_a_continuation_alone(script):
    snapshot = {"issueId": "issue-1", "paperclipWake": {"issue": {"id": "issue-1"}}}
    assert script.slim_snapshot(snapshot) == snapshot


def test_the_reference_leaves_a_continuation_without_messages_alone(script):
    snapshot = {"executionContinuation": {"originCommentIds": ["c1"]}}
    assert script.slim_snapshot(snapshot) == snapshot


def test_the_reference_leaves_a_snapshot_that_is_not_an_object_alone(script):
    assert script.slim_snapshot(None) is None
    assert script.slim_snapshot("text") == "text"
    assert script.slim_snapshot([1, 2]) == [1, 2]


def test_the_reference_is_idempotent(script):
    once = script.slim_snapshot(_snapshot())
    assert script.slim_snapshot(once) == once


def test_the_digest_is_the_value_the_database_computes(script):
    snapshot = {"executionContinuation": {"messages": [{"body": "hello"}]}}
    slim = script.slim_snapshot(snapshot)
    assert slim["executionContinuation"]["messages"][0]["bodyDigest"] == HELLO_DIGEST
    assert hashlib.sha256(b"hello").hexdigest() == HELLO_DIGEST


# --------------------------------------------------------------------------
# The pinned copy of the trigger
# --------------------------------------------------------------------------


def test_the_pinned_copy_carries_the_trigger_body(script):
    sql = script.build_pinned_trigger_sql()
    assert (
        "CREATE OR REPLACE FUNCTION pg_temp."
        "paperclip_slim_heartbeat_run_context_snapshot_pinned()" in sql
    )
    assert "RETURNS trigger" in sql
    assert "jsonb_array_elements" in sql
    assert (
        "encode(sha256(convert_to(element.message ->> 'body', 'UTF8')), 'hex')" in sql
    )
    assert "'bodyDigest'" in sql
    assert "NEW.context_issue_id := slim_snapshot ->> 'issueId'" in sql
    assert "NEW.context_task_id := slim_snapshot ->> 'taskId'" in sql


def test_the_pinned_copy_removes_only_the_continuation_keys_and_the_body(script):
    sql = script.build_pinned_trigger_sql()
    removed = set(re.findall(r"- '([^']+)'::text", sql))
    # The body of a message is replaced by its digest, and the two
    # continuation keys are taken out before they are built again.
    assert removed == {"body", "messages", "executionContinuation"}


def test_the_pinned_copy_drops_nothing_else(script):
    sql = script.build_pinned_trigger_sql()
    # The trigger keeps the wake payload and the rendered prompt. A drop list
    # for them would be the old, aggressive transform coming back.
    for key in ("paperclipTaskMarkdown", "paperclipWake", "continuationSummary"):
        assert key not in sql


def test_the_pinned_copy_stays_out_of_the_schema(script):
    sql = script.build_pinned_trigger_sql()
    assert "pg_temp." in sql
    assert "CREATE OR REPLACE FUNCTION public." not in sql
    assert "DROP FUNCTION" not in sql


def test_the_pinned_copy_names_its_source(script):
    assert "1c918d30b" in script.PINNED_TRIGGER_SOURCE
    assert "0308_heartbeat_run_context_columns.sql" in script.PINNED_TRIGGER_SOURCE


# --------------------------------------------------------------------------
# The probe: a session-local copy of the table that carries the trigger
# --------------------------------------------------------------------------


def test_the_probe_is_a_session_local_copy_of_the_table(script):
    sql = script.build_probe_sql(script.PROBE_TABLE)
    assert "CREATE TEMP TABLE" in sql
    assert "pg_temp.paperclip_slim_probe" in sql
    assert "WITH NO DATA" in sql
    assert "context_issue_id text" in sql
    assert "context_task_id text" in sql


def test_the_probe_runs_the_chosen_function(script):
    sql = script.build_probe_trigger_sql(script.PROBE_TABLE, "public.paperclip_x")
    assert "BEFORE INSERT ON pg_temp.paperclip_slim_probe" in sql
    assert "EXECUTE FUNCTION public.paperclip_x()" in sql


def test_the_script_does_not_implement_a_second_transform(script):
    text = _SCRIPT.read_text(encoding="utf-8")
    # The old twin of the trigger is gone: the script runs the trigger.
    assert "pg_temp.paperclip_slim_snapshot" not in text
    assert "drop_continuation" not in text
    assert "--drop-continuation" not in text


# --------------------------------------------------------------------------
# The batched write
# --------------------------------------------------------------------------


def test_the_batch_walks_the_table_with_a_cursor(script):
    sql = script.build_batch_load_sql()
    assert "id > %(cursor)s" in sql
    assert "ORDER BY id" in sql
    assert "LIMIT %(batch_size)s" in sql


def test_the_batch_writes_through_the_probe(script):
    load = script.build_batch_load_sql()
    assert "INSERT INTO pg_temp.paperclip_slim_probe" in load
    assert "SELECT id, context_snapshot, context_snapshot" in load
    update = script.build_batch_update_sql(set_id_columns=False)
    assert "FROM pg_temp.paperclip_slim_probe AS p" in update


def test_the_load_is_a_statement_of_its_own(script):
    """The write must not read its value from a data-modifying CTE.

    An `UPDATE` that reads from a data-modifying CTE runs that CTE again
    when a row of the target table was updated concurrently, and PostgreSQL
    refuses to write inside that re-check: "ModifyTable should not be called
    during EvalPlanQual". The table of a live instance is written while this
    script runs, so the write reads from a table instead.
    """
    update = script.build_batch_update_sql(set_id_columns=False)
    assert "MATERIALIZED" not in update
    assert "INSERT INTO" not in update
    assert "WITH upd AS" in update


def test_the_probe_keeps_the_value_the_row_had(script):
    probe = script.build_probe_sql(script.PROBE_TABLE)
    assert "original_snapshot jsonb" in probe
    load = script.build_batch_load_sql()
    assert "original_snapshot" in load


def test_the_write_skips_a_row_that_the_instance_wrote_in_the_meantime(script):
    sql = script.build_batch_update_sql(set_id_columns=False)
    assert "r.context_snapshot IS NOT DISTINCT FROM p.original_snapshot" in sql


def test_the_batch_is_idempotent_by_comparison(script):
    sql = script.build_batch_update_sql(set_id_columns=False)
    assert "IS DISTINCT FROM" in sql


def test_the_batch_sets_the_id_columns_only_when_they_exist(script):
    with_columns = script.build_batch_update_sql(set_id_columns=True)
    assert "context_issue_id = p.context_issue_id" in with_columns
    assert "context_task_id = p.context_task_id" in with_columns
    without_columns = script.build_batch_update_sql(set_id_columns=False)
    assert "context_issue_id =" not in without_columns
    assert "context_task_id =" not in without_columns


def test_the_dry_run_counts_instead_of_writing(script):
    sql = script.build_batch_dry_run_sql()
    assert "UPDATE heartbeat_runs" not in sql
    assert "IS DISTINCT FROM" in sql
    assert "pg_temp.paperclip_slim_probe" in sql


def test_the_cursor_never_uses_max_on_a_uuid(script):
    sql = script.build_batch_update_sql(set_id_columns=False)
    assert "max(id)" not in sql
    assert "ORDER BY id DESC LIMIT 1" in sql


def test_the_dry_run_advances_the_cursor(script):
    assert "AS last_id" in script.build_batch_dry_run_sql()


def test_a_batch_that_runs_into_a_concurrent_write_is_retried(script):
    assert script.BATCH_ATTEMPTS >= 2
    assert "40001" in script.RETRYABLE_SQLSTATES
    assert "XX000" in script.RETRYABLE_SQLSTATES


# --------------------------------------------------------------------------
# The connection
# --------------------------------------------------------------------------


def test_the_password_never_enters_the_connection_string(script):
    conninfo, kwargs = script.resolve_connection(_args(), {"PGPASSWORD": "s3cret"})
    assert "s3cret" not in conninfo
    assert kwargs == {"password": "s3cret"}


def test_the_dsn_environment_variable_wins(script):
    conninfo, kwargs = script.resolve_connection(
        _args(dsn="postgres://x/y"), {"PGPASSWORD": "s3cret"}
    )
    assert conninfo == "postgres://x/y"
    assert kwargs == {}


def test_redact_dsn_hides_the_password(script):
    assert "s3cret" not in script.redact_dsn("postgres://user:s3cret@host:5432/db")
    assert "s3cret" not in script.redact_dsn("host=db password=s3cret")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def test_format_bytes_reads_the_scale(script):
    assert script.format_bytes(512) == "512 B"
    assert "KiB" in script.format_bytes(2048)
    assert "MiB" in script.format_bytes(5 * 1024 * 1024)


def test_resolve_cutoff_is_infinite_without_an_age_limit(script):
    assert script.resolve_cutoff(0) == "infinity"


# --------------------------------------------------------------------------
# The credential guard
# --------------------------------------------------------------------------


def test_the_script_holds_no_password_literal(script):
    text = _SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"password\s*=\s*[\"'][^\"']+[\"']", text)
    assert "PGPASSWORD" in text


def test_the_script_never_prints_the_password(script):
    text = _SCRIPT.read_text(encoding="utf-8")
    # The value read from the environment never reaches a print call.
    for line in text.splitlines():
        if "print(" in line:
            assert "secret" not in line
            assert "connect_kwargs" not in line
            assert "kwargs" not in line


def test_the_credential_guard_does_not_flag_the_script():
    result = subprocess.run(
        [sys.executable, str(_GUARD), str(_SCRIPT)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_verification_payload_carries_the_rows():
    payload = json.dumps([{"id": "row-1", "context_snapshot": {"issueId": "issue-1"}}])
    assert json.loads(payload)[0]["id"] == "row-1"
