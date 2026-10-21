"""Unit tests for the heartbeat_runs snapshot cleanup (DIG-4821)."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "paperclip_heartbeat_runs_slim.py"


def _load():
    spec = importlib.util.spec_from_file_location("paperclip_heartbeat_runs_slim", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["paperclip_heartbeat_runs_slim"] = module
    spec.loader.exec_module(module)
    return module


def _args(**overrides) -> argparse.Namespace:
    base = {
        "dsn": "",
        "host": "127.0.0.1",
        "port": 54329,
        "user": "paperclip",
        "dbname": "paperclip",
        "password_env": "PGPASSWORD",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


# --------------------------------------------------------------------------
# The transform
# --------------------------------------------------------------------------


def test_drops_the_rendered_prompt_copies() -> None:
    """The markdown copies are rebuilt at dispatch time; storing them is the fat."""
    slim = _load()
    snapshot = {
        "issueId": "issue-1",
        "taskId": "task-1",
        "paperclipTaskMarkdown": "# rendered",
        "paperclipTaskMarkdownCompact": "# rendered compact",
        "paperclipTaskMarkdownAssignment": "# assignment",
        "paperclipTaskMarkdownAssignmentCompact": "# assignment compact",
        "paperclipWakeComment": "# comment",
        "paperclipFreshSessionHandoffMarkdown": "# handoff",
    }
    result = slim.slim_snapshot(snapshot)
    assert result == {"issueId": "issue-1", "taskId": "task-1"}


def test_keeps_the_top_level_continuation_by_default() -> None:
    """The resume path reads it, so the default keeps it."""
    slim = _load()
    snapshot = {
        "executionContinuation": {"messages": [{"id": "m1"}]},
        "paperclipContinuationSummary": {},
    }
    result = slim.slim_snapshot(snapshot)
    assert result["executionContinuation"] == {"messages": [{"id": "m1"}]}
    assert "paperclipContinuationSummary" in result


def test_drops_the_top_level_continuation_on_request() -> None:
    slim = _load()
    snapshot = {"executionContinuation": {"messages": []}, "paperclipContinuationSummary": {"a": 1}}
    result = slim.slim_snapshot(snapshot, drop_continuation=True)
    assert result == {}


def test_drops_the_wake_copies() -> None:
    slim = _load()
    snapshot = {
        "paperclipWake": {
            "executionContinuation": {"messages": []},
            "continuationSummary": {"text": "x"},
            "reason": "issue_commented",
        }
    }
    result = slim.slim_snapshot(snapshot)
    assert result["paperclipWake"] == {"reason": "issue_commented"}


def test_reduces_the_wake_issue_to_its_id() -> None:
    slim = _load()
    snapshot = {"paperclipWake": {"issue": {"id": "issue-9", "title": "t", "body": "b"}}}
    result = slim.slim_snapshot(snapshot)
    assert result["paperclipWake"]["issue"] == {"id": "issue-9"}


def test_leaves_a_wake_issue_without_an_id_alone() -> None:
    slim = _load()
    snapshot = {"paperclipWake": {"issue": {"title": "t"}}}
    result = slim.slim_snapshot(snapshot)
    assert result["paperclipWake"]["issue"] == {"title": "t"}


def test_leaves_a_snapshot_without_a_wake_alone() -> None:
    slim = _load()
    snapshot = {"issueId": "issue-1", "paperclipWake": "not-an-object"}
    assert slim.slim_snapshot(snapshot) == snapshot


def test_is_idempotent() -> None:
    slim = _load()
    snapshot = {
        "issueId": "issue-1",
        "paperclipTaskMarkdown": "# rendered",
        "paperclipWake": {
            "executionContinuation": {"messages": []},
            "issue": {"id": "issue-1", "title": "t"},
        },
    }
    once = slim.slim_snapshot(snapshot)
    assert slim.slim_snapshot(once) == once


# --------------------------------------------------------------------------
# The SQL twin
# --------------------------------------------------------------------------


def _drops(sql: str, key: str, indent: int) -> int:
    """How often the SQL drops a key at one indent level.

    The top level drops are indented by four spaces, the wake drops by six, so
    the same key name can be counted in each place on its own.
    """
    return sql.count("\n" + " " * indent + f"- '{key}'::text")


def test_sql_function_drops_the_same_keys_as_the_reference() -> None:
    slim = _load()
    sql = slim.build_slim_function_sql()
    for key in slim.TOP_LEVEL_MARKDOWN_KEYS:
        assert _drops(sql, key, 4) == 1
    for key in slim.TOP_LEVEL_CONTINUATION_KEYS:
        assert _drops(sql, key, 4) == 0
    for key in slim.WAKE_DROP_KEYS:
        assert _drops(sql, key, 6) == 1


def test_sql_function_drops_the_continuation_on_request() -> None:
    slim = _load()
    sql = slim.build_slim_function_sql(drop_continuation=True)
    for key in slim.TOP_LEVEL_CONTINUATION_KEYS:
        assert _drops(sql, key, 4) == 1
    for key in slim.WAKE_DROP_KEYS:
        assert _drops(sql, key, 6) == 1


def test_sql_function_stays_out_of_the_schema() -> None:
    """A session-local function leaves nothing behind in the database."""
    slim = _load()
    assert "pg_temp.paperclip_slim_snapshot" in slim.build_slim_function_sql()
    assert "CREATE OR REPLACE FUNCTION public." not in slim.build_slim_function_sql()


def test_batch_update_walks_the_table_with_a_cursor() -> None:
    slim = _load()
    sql = slim.build_batch_update_sql(set_id_columns=False)
    assert "id > %(cursor)s" in sql
    assert "ORDER BY id" in sql
    assert "LIMIT %(batch_size)s" in sql
    assert "AS MATERIALIZED" in sql


def test_batch_update_is_idempotent_by_comparison() -> None:
    """A row that is already slim must not be written again."""
    slim = _load()
    sql = slim.build_batch_update_sql(set_id_columns=False)
    assert "s.slim IS DISTINCT FROM s.original" in sql


def test_batch_update_sets_the_id_columns_only_when_they_exist() -> None:
    slim = _load()
    without = slim.build_batch_update_sql(set_id_columns=False)
    with_columns = slim.build_batch_update_sql(set_id_columns=True)
    assert "context_issue_id" not in without
    assert "context_issue_id" in with_columns
    assert "context_task_id" in with_columns


def test_dry_run_query_counts_instead_of_writing() -> None:
    slim = _load()
    sql = slim.build_batch_dry_run_sql()
    assert not re.search(r"\bUPDATE\s+heartbeat_runs", sql, re.IGNORECASE)
    assert "IS DISTINCT FROM" in sql


def test_the_cursor_never_uses_max_on_a_uuid() -> None:
    """`max()` is not defined for uuid, so the cursor is the last id by order."""
    slim = _load()
    for sql in (slim.build_batch_update_sql(set_id_columns=False), slim.build_batch_dry_run_sql()):
        assert "max(id)" not in sql
        assert "ORDER BY id DESC LIMIT 1" in sql


def test_the_dry_run_advances_the_cursor() -> None:
    """A dry run that never moves the cursor counts the same rows forever."""
    slim = _load()
    assert "AS last_id" in slim.build_batch_dry_run_sql()
    assert "AS last_id" in slim.build_batch_update_sql(set_id_columns=False)


# --------------------------------------------------------------------------
# The connection and the report
# --------------------------------------------------------------------------


def test_the_password_never_enters_the_connection_string() -> None:
    """A command line password would land in the process list."""
    slim = _load()
    conninfo, kwargs = slim.resolve_connection(_args(), {"PGPASSWORD": "s3cret"})
    assert "s3cret" not in conninfo
    assert kwargs == {"password": "s3cret"}


def test_the_dsn_environment_variable_wins() -> None:
    slim = _load()
    conninfo, kwargs = slim.resolve_connection(
        _args(), {"PAPERCLIP_DATABASE_URL": "postgresql://u@h/db", "PGPASSWORD": "s3cret"}
    )
    assert conninfo == "postgresql://u@h/db"
    assert kwargs == {}


def test_redact_dsn_hides_the_password() -> None:
    slim = _load()
    assert "s3cret" not in slim.redact_dsn(
        "postgresql://paperclip:s3cret@127.0.0.1:54329/paperclip"
    )
    assert "password=***" in slim.redact_dsn("host=127.0.0.1 password=s3cret dbname=paperclip")


def test_format_bytes_reads_the_scale() -> None:
    slim = _load()
    assert slim.format_bytes(512) == "512 B"
    assert slim.format_bytes(1024) == "1.00 KiB"
    assert "GiB" in slim.format_bytes(2_723_749_888)


def test_resolve_cutoff_is_infinite_without_an_age_limit() -> None:
    slim = _load()
    assert slim.resolve_cutoff(0) == "infinity"
    assert slim.resolve_cutoff(7).tzinfo is not None


def test_the_script_holds_no_password_literal() -> None:
    """A secret must never be committed in the script."""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"password\s*=\s*[\"'][^\"']+[\"']", text)
    assert "PGPASSWORD" in text


def test_the_script_never_prints_the_password() -> None:
    slim = _load()
    assert "s3cret" not in slim.redact_dsn("postgresql://paperclip:s3cret@h/db")
