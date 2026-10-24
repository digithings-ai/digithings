"""Tests for scripts/paperclip_heartbeat_runs_redact_secrets.py.

The bearer class belongs to the paperclip server: DIG-5227 puts the server's
own `redactEventPayload` on the run result write path. This script scrubs the
rows that were written before that landed, so it must run the server's rule
instead of carrying a second rule of its own - a second rule would drift
without anybody noticing.

These tests pin that: the script runs the server's module, the pinned detector
agrees with the server's helper, a row without a bearer value is never
written, a dry run writes nothing, the password comes from the environment,
and nothing that carries a credential is ever printed.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "paperclip_heartbeat_runs_redact_secrets.py"
_HARNESS = _REPO_ROOT / "scripts" / "paperclip_heartbeat_runs_redact_harness.mjs"
_SERVER_REPO = Path(
    os.environ.get("PAPERCLIP_SERVER_REPO", "~/Code/paperclip")
).expanduser()

# The shape of a bearer value. It is what the script looks for in the stored
# payloads, so it must not match anything that is written in the sources: a
# match there would mean a credential had been copied into the repository.
_CREDENTIAL_SHAPE = re.compile(
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
)


def _code_strings(path: Path) -> list[str]:
    """Every string literal in the module that is not a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docstrings:
                continue
            values.append(node.value)
    return values


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "paperclip_heartbeat_runs_redact_secrets", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load()


# --------------------------------------------------------------------------
# The server's rule is the rule that runs
# --------------------------------------------------------------------------


def test_the_script_names_the_servers_rule(script):
    assert script.SERVER_REDACTION_ENTRY == "server/src/redaction.ts"
    assert script.SERVER_REDACTION_EXPORT == "redactEventPayload"
    assert "server/src/redaction.ts" in script.SERVER_REDACTION_SOURCE
    assert "paperclip" in script.SERVER_REDACTION_SOURCE


def test_the_script_runs_the_servers_module(script):
    """The rule is bundled out of the server's checkout and executed."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "esbuild" in source
    assert "--bundle" in source
    assert "redactEventPayload" in _HARNESS.read_text(encoding="utf-8")


def test_the_script_does_not_carry_a_second_rule(script):
    """The script holds a detector, not a rule of its own.

    The server decides what a bearer value is and how it is marked. A copy of
    the server's tables inside this script would be a second rule, and it
    would drift from the server without anybody noticing.
    """
    source = _SCRIPT.read_text(encoding="utf-8")
    for name in (
        "SECRET_TEXT_HINTS",
        "SECRET_PAYLOAD_KEY_RE",
        "SECRET_FIELD_NAME_PATTERN",
        "redactStandaloneBearerCredentials",
        "redactAuthorizationCredentials",
        "sanitizeRecord",
    ):
        assert name not in source
    # The script never rewrites a payload by itself: it writes what the
    # server returned.
    assert "re.sub" not in source


def test_the_marker_is_the_servers_marker(script):
    assert script.REDACTED_VALUE == "***REDACTED***"


def test_the_harness_prints_no_payload(script):
    harness = _HARNESS.read_text(encoding="utf-8")
    assert "console.log" not in harness
    assert "console.error" not in harness
    assert "process.stdout.write" in harness
    assert "process.stderr.write" in harness
    # A JSON parse error quotes the text it choked on, so only the name of
    # the error may leave the harness.
    assert "error.name" in harness


# --------------------------------------------------------------------------
# The pinned detector agrees with the server's helper
# --------------------------------------------------------------------------


def test_the_detector_flags_a_credential(script):
    credential = script.synthetic_credential()
    assert script.looks_like_credential_jwt(credential)
    assert script.bearer_values(credential) == [credential]


def test_the_detector_leaves_ordinary_text_alone(script):
    ordinary = [
        "a" * 200,
        script.base64url("hello world"),
        "https://example.com/x?a=1&b=2",
        "Error: connection refused while calling upstream",
        "Bearer instance-token-name",
    ]
    for value in ordinary:
        assert not script.looks_like_credential_jwt(value)
        assert script.bearer_values(value) == []


def test_the_detector_finds_a_value_embedded_in_a_long_text(script):
    credential = script.synthetic_credential()
    text = "the run printed a lot of output " * 50 + credential + "\nand stopped"
    hits = script.find_bearer_values({"stdout": text})
    assert hits
    assert hits[0][0] == "stdout"
    assert hits[0][1] == [credential]


def test_the_detector_finds_a_value_it_has_never_seen(script):
    """The values are found by shape, not by matching a known value."""
    header = script.base64url(json.dumps({"alg": "RS256", "typ": "JWT"}))
    claims = script.base64url(json.dumps({"sub": "another-agent", "exp": 0}))
    signature = script.base64url("a signature nobody has seen before")
    fresh = f"{header}.{claims}.{signature}"
    assert fresh != script.synthetic_credential()
    assert script.looks_like_credential_jwt(fresh)


def test_the_expiry_is_read_from_the_claim(script):
    header = script.base64url(json.dumps({"alg": "HS256"}))
    claims = script.base64url(json.dumps({"exp": 4102444800}))
    value = f"{header}.{claims}.{script.base64url('signature')}"
    assert script.jwt_expiry(value) == 4102444800.0
    assert script.jwt_expiry("not a credential") is None


def test_the_sources_carry_no_credential(script):
    for path in (_SCRIPT, _HARNESS):
        assert not _CREDENTIAL_SHAPE.search(path.read_text(encoding="utf-8"))


def test_the_server_rule_agrees_with_the_pinned_detector(script, tmp_path):
    """The proof the scrub needs: the two rules agree on the fixture.

    The server's rule has to take the bearer fixtures apart with the server's
    marker and leave the ordinary fixtures exactly as they were.
    """
    if not (_SERVER_REPO / script.SERVER_REDACTION_ENTRY).is_file():
        pytest.skip("the paperclip checkout is not available here")
    rule = script.ServerRule(_SERVER_REPO, _HARNESS, tmp_path)
    try:
        rule.prepare()
        assert script.check_fixture(rule)["fixture_paths"] == len(
            script.FIXTURE_BEARER_PATHS
        )
    finally:
        rule.close()


# --------------------------------------------------------------------------
# The write
# --------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: dict | None = None) -> None:
        self._conn.statements.append(sql)

    def fetchall(self) -> list:
        return self._conn.rows


class _FakeTransaction:
    def __enter__(self) -> _FakeTransaction:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class _FakeConnection:
    def __init__(self, rows: list) -> None:
        self.rows = rows
        self.statements: list[str] = []
        self.transactions = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def transaction(self) -> _FakeTransaction:
        self.transactions += 1
        return _FakeTransaction()


class _FakeRule:
    """Stands in for the server's rule."""

    def __init__(self, redacted: dict) -> None:
        self.redacted = redacted

    def redact_many(self, payloads: list) -> list:
        return [self.redacted for _ in payloads]


def test_the_write_is_guarded_by_the_value_the_row_had(script):
    sql = script.build_write_sql()
    assert "heartbeat_runs" in sql
    assert "IS NOT DISTINCT FROM" in sql
    assert "RETURNING id" in sql


def test_the_batch_writes_in_one_transaction(script):
    credential = script.synthetic_credential()
    payload = {"stdout": f"before {credential} after"}
    redacted = {"stdout": f"before {script.REDACTED_VALUE} after"}
    row_id = uuid.uuid4()
    conn = _FakeConnection([(row_id, payload)])
    rewritten, skipped = script.write_batch(conn, [(row_id, payload, redacted)])
    assert (rewritten, skipped) == (1, 0)
    assert conn.transactions == 1
    assert any("IS NOT DISTINCT FROM" in statement for statement in conn.statements)


def test_the_dry_run_writes_nothing(script):
    credential = script.synthetic_credential()
    payload = {"stdout": f"before {credential} after"}
    redacted = {"stdout": f"before {script.REDACTED_VALUE} after"}
    conn = _FakeConnection([(uuid.uuid4(), payload)])
    args = argparse.Namespace(
        max_batches=1, batch_size=10, dry_run=True, pause_seconds=0.0
    )
    report = script.run_scrub(conn, _FakeRule(redacted), args)
    assert report["rows_scanned"] == 1
    assert report["rows_with_a_bearer_value"] == 1
    assert report["values_found"] == 1
    assert report["rows_rewritten"] == 0
    assert conn.transactions == 0
    assert not any("UPDATE" in statement for statement in conn.statements)


def test_the_report_carries_counts_only(script):
    credential = script.synthetic_credential()
    payload = {"stdout": f"before {credential} after"}
    redacted = {"stdout": f"before {script.REDACTED_VALUE} after"}
    conn = _FakeConnection([(uuid.uuid4(), payload)])
    args = argparse.Namespace(
        max_batches=1, batch_size=10, dry_run=True, pause_seconds=0.0
    )
    report = script.run_scrub(conn, _FakeRule(redacted), args)
    assert report
    for key, value in report.items():
        assert isinstance(value, int), key
    assert "payload" not in json.dumps(report).lower()
    assert credential not in json.dumps(report)


def test_a_row_without_a_bearer_value_is_not_written(script):
    """A row that holds no bearer value is left alone, so a second run
    rewrites nothing."""
    payload = {"stdout": "the run printed some output"}
    conn = _FakeConnection([(uuid.uuid4(), payload)])
    args = argparse.Namespace(
        max_batches=1, batch_size=10, dry_run=False, pause_seconds=0.0
    )
    report = script.run_scrub(conn, _FakeRule(payload), args)
    assert report["rows_with_a_bearer_value"] == 0
    assert report["values_found"] == 0
    assert report["rows_rewritten"] == 0
    assert conn.transactions == 0
    assert not any("UPDATE" in statement for statement in conn.statements)


# --------------------------------------------------------------------------
# The connection and the vacuum
# --------------------------------------------------------------------------


def test_the_password_comes_from_the_environment(script):
    args = script.parse_args([])
    assert "password" not in vars(args)
    assert '"--password"' not in _SCRIPT.read_text(encoding="utf-8")
    conninfo, kwargs = script.resolve_connection(args, {"PGPASSWORD": "s3cret"})
    assert kwargs["password"] == "s3cret"
    assert "s3cret" not in conninfo


def test_the_dsn_comes_from_the_environment(script):
    args = script.parse_args([])
    dsn = "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip"
    conninfo, kwargs = script.resolve_connection(args, {script.DSN_ENV: dsn})
    assert conninfo == dsn
    assert kwargs == {}


def test_the_dsn_is_redacted_before_it_is_printed(script):
    dsn = "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip"
    assert script.redact_dsn(dsn) == (
        "postgres://paperclip:***@127.0.0.1:54329/paperclip"
    )


def test_the_script_has_no_vacuum_full(script):
    """A VACUUM FULL rewrites the table under an ACCESS EXCLUSIVE lock.

    The prose may name it, the code may not: no string the script can run may
    ask for one.
    """
    for value in _code_strings(_SCRIPT):
        assert "vacuum full" not in value.lower()
    statements = " ".join(_code_strings(_SCRIPT))
    assert "VACUUM (ANALYZE)" in statements
