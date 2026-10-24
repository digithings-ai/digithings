#!/usr/bin/env python3
"""Scrub the bearer values out of paperclip's heartbeat_runs.result_json (DIG-5228).

A run result carries the agent's own run token in the text of its stdout, and
the token was stored as it was printed: `heartbeat_runs.result_json` holds the
value in the clear, in rows that were written before the server learned to
redact it. The value is a credential, so this script takes it out of the rows
that already exist.

It finds the values by shape and never by matching a known one, and it never
prints a value: not on stdout, not in the report, not in an error message. The
report carries counts only.

The rule is not written here. The server owns it: paperclip redacts a run
result with `redactEventPayload` from `server/src/redaction.ts` - the helper
it already runs on the run event write path, and the one DIG-5227 puts on the
run result write path. This script bundles that module out of the paperclip
checkout and runs it against the live rows, so the value it stores is the
value the server itself would have stored.

A pinned copy of the server's bearer detector lives here in Python
(`looks_like_credential_jwt`), because two questions need an answer the server
cannot give: which rows hold a bearer value, and whether the server's rule and
the pinned copy agree. The two are compared before anything is written - once
on a synthetic fixture, once on a sample of the live rows - and the script
refuses to write when they disagree. A rule that is written twice and never
compared drifts; this one cannot drift unnoticed.

It is idempotent: a row with no bearer value is not written, and a row whose
bearer value is gone holds none any more, so a second run rewrites nothing.

Usage:

    PGPASSWORD=... python scripts/paperclip_heartbeat_runs_redact_secrets.py --dry-run
    PGPASSWORD=... python scripts/paperclip_heartbeat_runs_redact_secrets.py

The password is never a command line argument. It is read from an environment
variable, so it lands neither in the shell history nor in the process list.

See docs/ops/heartbeat-runs-retention.md for the retention policy and for
this scrub.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

DSN_ENV = "PAPERCLIP_DATABASE_URL"
DEFAULT_PASSWORD_ENV = "PGPASSWORD"

RUNS_TABLE = "heartbeat_runs"
RESULT_COLUMN = "result_json"

# The marker the paperclip server writes: `REDACTED_EVENT_VALUE` and
# `REDACTED_COMMAND_TEXT_VALUE` in server/src/redaction.ts. It is the marker
# DIG-5227 puts on the run result write path, and the one this script checks
# the server's rule against.
REDACTED_VALUE = "***REDACTED***"

# The server's rule is run from the paperclip checkout, not copied here. The
# environment variable overrides the default path.
SERVER_REPO_ENV = "PAPERCLIP_SERVER_REPO"
DEFAULT_SERVER_REPO = "~/Code/paperclip"
SERVER_REDACTION_ENTRY = "server/src/redaction.ts"
SERVER_REDACTION_SOURCE = "digithings-ai/paperclip@21b3a07b, server/src/redaction.ts"
SERVER_REDACTION_EXPORT = "redactEventPayload"

# The node harness that runs the server's rule. It lives beside this script so
# it is read together with it.
HARNESS_NAME = "paperclip_heartbeat_runs_redact_harness.mjs"

# A live table is written while this script runs. PostgreSQL answers a write
# that ran into a concurrent change with one of these SQLSTATEs, and the batch
# is safe to run again, so the batch is retried a few times before the run
# gives up.
BATCH_ATTEMPTS = 3
RETRYABLE_SQLSTATES = frozenset({"40001", "40P01", "55P03", "XX000"})

# The SQL prefilter. It keeps every row that can hold a bearer value and more:
# the server needs three base64url segments of eight characters or more, and
# it needs them to look like a credential. The prefilter only saves reads -
# every candidate is checked again by the pinned detector.
CANDIDATE_PATTERN = r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"


class RuleUnavailable(RuntimeError):
    """The server's rule cannot be run, so nothing may be written."""


class DriftError(RuntimeError):
    """The server's rule and the pinned detector disagree, so nothing may be written."""


# --------------------------------------------------------------------------
# The pinned bearer detector
# --------------------------------------------------------------------------


JWT_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")

# The server's `COMMAND_JWT_RE`, from
# packages/adapter-utils/src/command-redaction.ts, unchanged.
COMMAND_JWT_RE = re.compile(
    r"\b[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,}){2}"
    r"(?:\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})?\b",
    re.ASCII,
)


def _decode_base64url(segment: str) -> bytes:
    """The bytes of a base64url segment, the way `atob` decodes it."""
    normalized = segment.replace("-", "+").replace("_", "/")
    padded = normalized + "=" * ((-len(normalized)) % 4)
    return base64.b64decode(padded, validate=True)


def looks_like_credential_jwt(value: str) -> bool:
    """The server's bearer shape, pinned.

    This is `looksLikeCredentialJwt` from
    packages/adapter-utils/src/command-redaction.ts, unchanged: three or five
    base64url segments of at least eight characters, and a first segment that
    is either `eyJ` (the base64url of a JSON object) or decodes to a JSON
    header carrying `alg`.

    It is the detector, not the transform. The transform is the server's own
    code, run from the server's own checkout.
    """
    segments = value.split(".")
    if len(segments) not in (3, 5):
        return False
    if not all(JWT_SEGMENT_RE.match(segment) for segment in segments):
        return False
    if segments[0].startswith("eyJ"):
        return True
    try:
        header = json.loads(_decode_base64url(segments[0]).decode("latin-1"))
    except Exception:
        return False
    return isinstance(header, dict) and isinstance(header.get("alg"), str)


def bearer_values(text: str) -> list[str]:
    """The bearer values a string carries.

    A string that is itself a credential carries one value. A string that
    carries a credential inside it - the run result's stdout does - carries
    one value per embedded token the server's own regex finds and the pinned
    shape accepts.

    The values are returned so their expiry can be read. They are never
    printed: the report says how many are still inside their own TTL, not
    which they are and not when they expire.
    """
    if looks_like_credential_jwt(text):
        return [text]
    values = []
    for match in COMMAND_JWT_RE.finditer(text):
        candidate = match.group(0)
        if looks_like_credential_jwt(candidate):
            values.append(candidate)
    return values


def iter_strings(payload: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Every string leaf of a payload, with the path it sits at."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{path}.{key}" if path else str(key)
            yield from iter_strings(value, child)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from iter_strings(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        yield path, payload


def find_bearer_values(payload: Any) -> list[tuple[str, list[str]]]:
    """The paths that carry a bearer value, and the values they carry."""
    found = []
    for path, text in iter_strings(payload):
        values = bearer_values(text)
        if values:
            found.append((path, values))
    return found


def jwt_expiry(value: str) -> float | None:
    """The `exp` claim of a credential, or None when there is none to read.

    The claim is read, never printed. The report counts the values that are
    still inside their own TTL; it does not say when they expire.
    """
    segments = value.split(".")
    if len(segments) < 2:
        return None
    try:
        claims = json.loads(_decode_base64url(segments[1]).decode("latin-1"))
    except Exception:
        return None
    if not isinstance(claims, dict):
        return None
    expiry = claims.get("exp")
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        return None
    return float(expiry)


def base64url(raw: str) -> str:
    """base64url without the padding, the way a token carries it."""
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


# --------------------------------------------------------------------------
# The server's rule, run from the server's own code
# --------------------------------------------------------------------------


class ServerRule:
    """The paperclip server's own redaction rule, run from its own source.

    The module is bundled out of the checkout with the checkout's own esbuild:
    the workspace resolves its packages by their `.js` specifiers, so node
    cannot run the TypeScript sources directly. The bundle is a build artifact
    of the server's source, not a copy of it - the rule that runs is the rule
    that is in the checkout.
    """

    def __init__(self, server_repo: Path, harness: Path, workdir: Path):
        self.server_repo = server_repo
        self.harness = harness
        self.workdir = workdir
        self._bundle: Path | None = None
        self._process: subprocess.Popen[str] | None = None
        self._stderr: list[str] = []

    def prepare(self) -> Path:
        """Bundle the server's redaction module. Fails closed."""
        entry = self.server_repo / SERVER_REDACTION_ENTRY
        if not entry.is_file():
            raise RuleUnavailable(
                f"the paperclip checkout at {self.server_repo} does not carry "
                f"{SERVER_REDACTION_ENTRY}; the server's rule cannot be run, "
                "so nothing is written"
            )
        esbuild = self._find_esbuild()
        bundle = self.workdir / "redaction.cjs"
        result = subprocess.run(
            [
                str(esbuild),
                str(entry),
                "--bundle",
                "--platform=node",
                "--format=cjs",
                f"--outfile={bundle}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not bundle.is_file():
            raise RuleUnavailable(
                "esbuild could not bundle the server's redaction module; "
                "the server's rule cannot be run, so nothing is written"
            )
        self._bundle = bundle
        return bundle

    def _find_esbuild(self) -> Path:
        local = self.server_repo / "node_modules" / ".bin" / "esbuild"
        if local.is_file():
            return local
        found = shutil.which("esbuild")
        if found:
            return Path(found)
        raise RuleUnavailable(
            "esbuild is not in the paperclip checkout and not on the PATH; "
            "the server's rule cannot be run, so nothing is written"
        )

    def _start(self) -> None:
        if self._process is not None:
            return
        if self._bundle is None:
            self.prepare()
        node = shutil.which("node")
        if not node:
            raise RuleUnavailable(
                "node is not on the PATH; the server's rule cannot be run, "
                "so nothing is written"
            )
        self._process = subprocess.Popen(
            [node, str(self.harness), str(self._bundle)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        """Keep the harness's error names, and nothing else."""
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr.append(line.rstrip("\n"))
            if len(self._stderr) > 20:
                self._stderr.pop(0)

    def redact_many(self, payloads: list[Any]) -> list[Any]:
        """The server's rule, run over a batch of payloads."""
        if not payloads:
            return []
        self._start()
        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise RuleUnavailable("the server's rule did not start; nothing is written")
        lines = [json.dumps(payload) for payload in payloads]
        failure: list[BaseException] = []

        def write() -> None:
            try:
                for line in lines:
                    process.stdin.write(line + "\n")
                process.stdin.flush()
            except BaseException as exc:  # every failure is reported below
                failure.append(exc)

        # The payloads are written on their own thread: a payload is larger
        # than a pipe buffer, so writing and reading in the same thread would
        # deadlock the moment the harness answers with a redacted payload of
        # its own.
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        try:
            output = [process.stdout.readline() for _ in lines]
        finally:
            writer.join()
        if failure:
            raise RuleUnavailable(
                "the server's rule stopped answering; nothing is written "
                f"({type(failure[0]).__name__})"
            )
        results = []
        for line in output:
            if not line.strip():
                raise RuleUnavailable(
                    "the server's rule did not answer for every payload; "
                    "nothing is written"
                )
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise RuleUnavailable(
                    "the server's rule answered with something that is not a "
                    f"payload; nothing is written ({exc.msg})"
                ) from exc
        return results

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (process.stdin,):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()


# --------------------------------------------------------------------------
# The agreement between the server's rule and the pinned detector
# --------------------------------------------------------------------------


def synthetic_credential() -> str:
    """A synthetic credential, built here and nowhere else.

    Every part of it is made up: a fixed header, a fixed set of claims and a
    fixed signature. It exists to be recognised, and it is not a credential
    of anything.
    """
    header = base64url(json.dumps({"alg": "HS256", "typ": "JWT"}))
    claims = base64url(
        json.dumps(
            {
                "sub": "00000000-0000-0000-0000-000000000000",
                "run_id": "00000000-0000-0000-0000-000000000001",
                "exp": 0,
            }
        )
    )
    signature = base64url("synthetic-signature")
    return f"{header}.{claims}.{signature}"


# The fixture: a synthetic payload with the cases the two rules have to agree
# on. The bearer cases carry the synthetic credential; the ordinary cases are
# the text the server has to leave alone.
FIXTURE_BEARER_PATHS = ("bare", "header_line", "nested.deep.value", "list[0]")
FIXTURE_ORDINARY_PATHS = ("long_text", "base64_blob", "url", "message")


def build_fixture() -> dict[str, Any]:
    """The synthetic payload the two rules are compared on."""
    credential = synthetic_credential()
    return {
        "bare": credential,
        "header_line": f"Authorization: Bearer {credential}",
        "nested": {"deep": {"value": credential}},
        "list": [credential, "plain text"],
        "long_text": "a" * 200,
        "base64_blob": base64url("hello world"),
        "url": "https://example.com/x?a=1&b=2",
        "message": "Error: connection refused while calling upstream",
    }


def check_fixture(rule: ServerRule) -> dict[str, Any]:
    """The two rules on the synthetic fixture.

    The pinned detector has to flag the bearer fixtures and only them. The
    server's rule has to take the bearer fixtures apart, with the server's
    marker, and leave the ordinary fixtures exactly as they were.
    """
    fixture = build_fixture()
    flagged = {path for path, _ in find_bearer_values(fixture)}
    if flagged != set(FIXTURE_BEARER_PATHS):
        raise DriftError(
            "the pinned bearer detector does not flag the synthetic bearer fixtures "
            f"and only them (it flagged {sorted(flagged)}); refusing to write"
        )
    redacted = rule.redact_many([fixture])[0]
    ordinary = dict(iter_strings(fixture))
    for path, value in iter_strings(redacted):
        if bearer_values(value):
            raise DriftError(
                f"the server's rule left a bearer-shaped value at {path} of the "
                "synthetic fixture; refusing to write"
            )
        if path in FIXTURE_ORDINARY_PATHS and value != ordinary.get(path):
            raise DriftError(
                f"the server's rule changed the ordinary fixture at {path}; "
                "refusing to write"
            )
    for path in FIXTURE_BEARER_PATHS:
        value = dict(iter_strings(redacted)).get(path, "")
        if REDACTED_VALUE not in value:
            raise DriftError(
                f"the server's rule did not mark the bearer fixture at {path} with "
                f"{REDACTED_VALUE}; refusing to write"
            )
    return {"fixture_paths": len(FIXTURE_BEARER_PATHS)}


def check_live_sample(
    conn: Any, rule: ServerRule, sample_size: int
) -> dict[str, Any]:
    """The two rules on the live rows.

    The server's rule is run over rows that hold a bearer value, and the
    pinned detector has to find nothing bearer-shaped in the result. That is
    the agreement the script needs: the server's rule takes every bearer
    value the pinned rule finds. When it does not, the two rules have drifted
    apart and the script refuses to write.
    """
    if sample_size <= 0:
        return {"compared": 0}
    cursor = uuid.UUID(int=0)
    compared = 0
    while compared < sample_size:
        batch = fetch_batch(conn, cursor, 25)
        if not batch:
            break
        cursor = batch[-1][0]
        flagged = [
            (row_id, payload)
            for row_id, payload in batch
            if find_bearer_values(payload)
        ]
        if not flagged:
            continue
        for (row_id, _payload), redacted in zip(
            flagged, rule.redact_many([payload for _, payload in flagged])
        ):
            left = find_bearer_values(redacted)
            if left:
                raise DriftError(
                    f"the server's rule and the pinned bearer detector disagree on row "
                    f"{row_id}: {len(left)} path(s) still carry a bearer-shaped value; "
                    "refusing to write"
                )
            compared += 1
            if compared >= sample_size:
                break
    return {"compared": compared}


# --------------------------------------------------------------------------
# The database
# --------------------------------------------------------------------------


def resolve_connection(args: argparse.Namespace, env: dict[str, str]) -> tuple[str, dict[str, str]]:
    """The connection string and the keyword arguments for psycopg.connect.

    The password comes from an environment variable, never from the command
    line, so it never appears in the process list.
    """
    dsn = (args.dsn or env.get(DSN_ENV) or "").strip()
    if dsn:
        return dsn, {}
    conninfo = f"host={args.host} port={args.port} dbname={args.dbname}"
    if args.user:
        conninfo += f" user={args.user}"
    secret = env.get(args.password_env, "")
    return conninfo, ({"password": secret} if secret else {})


def redact_dsn(dsn: str) -> str:
    """Hide the password in a DSN before it is printed."""
    if "://" in dsn:
        scheme, _, rest = dsn.partition("://")
        if "@" in rest:
            userinfo, _, hostpart = rest.rpartition("@")
            user, _, _password = userinfo.partition(":")
            return f"{scheme}://{user}:***@{hostpart}"
        return dsn
    parts = []
    for chunk in dsn.split():
        key, sep, _value = chunk.partition("=")
        parts.append(f"{key}=***" if sep and key == "password" else chunk)
    return " ".join(parts)


def build_scan_sql() -> str:
    """One batch of candidate rows.

    The prefilter keeps the rows whose text carries three base64url segments
    of eight characters or more, which is every row that can hold a bearer
    value and more. The pinned detector checks every candidate again, so the
    prefilter only saves reads.
    """
    return f"""
SELECT id, {RESULT_COLUMN}
  FROM {RUNS_TABLE}
 WHERE {RESULT_COLUMN} IS NOT NULL
   AND id > %(cursor)s
   AND {RESULT_COLUMN}::text ~ %(candidate)s
 ORDER BY id
 LIMIT %(batch_size)s
""".strip()


def build_write_sql() -> str:
    """The write of one row.

    The guard compares the value the row had when the batch was read with the
    value it has now. A row that the instance wrote in between is left alone:
    it carries a fresher result than the batch was built from, and overwriting
    it would lose what the instance wrote.
    """
    return f"""
UPDATE {RUNS_TABLE}
   SET {RESULT_COLUMN} = %(new_value)s::jsonb
 WHERE id = %(id)s
   AND {RESULT_COLUMN} IS NOT DISTINCT FROM %(old_value)s::jsonb
RETURNING id
""".strip()


def fetch_batch(conn: Any, cursor: uuid.UUID, batch_size: int) -> list[tuple[uuid.UUID, Any]]:
    """The next batch of candidate rows."""
    with conn.cursor() as cur:
        cur.execute(
            build_scan_sql(),
            {
                "cursor": cursor,
                "batch_size": batch_size,
                "candidate": CANDIDATE_PATTERN,
            },
        )
        return cur.fetchall()


def count_rows(conn: Any) -> int:
    """How many rows carry a result payload."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {RUNS_TABLE} WHERE {RESULT_COLUMN} IS NOT NULL"
        )
        return int(cur.fetchone()[0])


def write_batch(conn: Any, writes: list[tuple[uuid.UUID, Any, Any]]) -> tuple[int, int]:
    """Write one batch in one transaction.

    Returns the number of rows rewritten and the number of rows left alone
    because the instance had written them in the meantime.
    """
    sql = build_write_sql()
    for attempt in range(1, BATCH_ATTEMPTS + 1):
        rewritten = 0
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    for row_id, old_value, new_value in writes:
                        cur.execute(
                            sql,
                            {
                                "id": row_id,
                                "old_value": json.dumps(old_value),
                                "new_value": json.dumps(new_value),
                            },
                        )
                        rewritten += len(cur.fetchall())
            return rewritten, len(writes) - rewritten
        except Exception as exc:
            sqlstate = getattr(exc, "sqlstate", None)
            if attempt >= BATCH_ATTEMPTS or sqlstate not in RETRYABLE_SQLSTATES:
                raise
            print(
                f"  batch: {type(exc).__name__}; retrying ({attempt}/{BATCH_ATTEMPTS})",
                flush=True,
            )
            time.sleep(1.0)
    return 0, len(writes)


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def run_scrub(conn: Any, rule: ServerRule, args: argparse.Namespace) -> dict[str, Any]:
    """Walk the table once, in batches, and take the bearer values out."""
    cursor = uuid.UUID(int=0)
    rows_scanned = 0
    rows_with_value = 0
    values_found = 0
    values_inside_ttl = 0
    values_with_expiry = 0
    rows_rewritten = 0
    rows_skipped = 0
    batches = 0
    now = time.time()
    while True:
        if args.max_batches and batches >= args.max_batches:
            break
        batch = fetch_batch(conn, cursor, args.batch_size)
        if not batch:
            break
        batches += 1
        cursor = batch[-1][0]
        rows_scanned += len(batch)
        flagged = []
        for row_id, payload in batch:
            hits = find_bearer_values(payload)
            if not hits:
                continue
            flagged.append((row_id, payload))
            rows_with_value += 1
            for _path, values in hits:
                values_found += len(values)
                for value in values:
                    expiry = jwt_expiry(value)
                    if expiry is None:
                        continue
                    values_with_expiry += 1
                    if expiry > now:
                        values_inside_ttl += 1
        if not flagged:
            if args.pause_seconds > 0:
                time.sleep(args.pause_seconds)
            continue
        redacted = rule.redact_many([payload for _, payload in flagged])
        writes = []
        for (row_id, payload), new_payload in zip(flagged, redacted):
            left = find_bearer_values(new_payload)
            if left:
                raise DriftError(
                    f"the server's rule and the pinned bearer detector disagree on row "
                    f"{row_id}: {len(left)} path(s) still carry a bearer-shaped value; "
                    "refusing to write"
                )
            writes.append((row_id, payload, new_payload))
        if args.dry_run:
            print(
                f"  batch {batches}: scanned {len(batch)}, would rewrite {len(writes)}",
                flush=True,
            )
        else:
            rewritten, skipped = write_batch(conn, writes)
            rows_rewritten += rewritten
            rows_skipped += skipped
            print(
                f"  batch {batches}: scanned {len(batch)}, rewritten {rewritten}",
                flush=True,
            )
        if args.pause_seconds > 0:
            time.sleep(args.pause_seconds)
    return {
        "batches": batches,
        "rows_scanned": rows_scanned,
        "rows_with_a_bearer_value": rows_with_value,
        "values_found": values_found,
        "values_inside_ttl": values_inside_ttl,
        "values_with_an_expiry_claim": values_with_expiry,
        "rows_rewritten": rows_rewritten,
        "rows_skipped": rows_skipped,
    }


def count_values_left(conn: Any) -> int:
    """How many bearer values are still in the table.

    The script's own scan, run over the whole table again after the scrub.
    """
    cursor = uuid.UUID(int=0)
    left = 0
    while True:
        batch = fetch_batch(conn, cursor, 50)
        if not batch:
            break
        cursor = batch[-1][0]
        for _row_id, payload in batch:
            left += sum(len(values) for _path, values in find_bearer_values(payload))
    return left


def run_vacuum(conn: Any, *, lock_timeout_ms: int) -> str:
    """Reclaim the dead tuples.

    Plain VACUUM returns the space to the free space map for reuse but keeps
    the files. There is no VACUUM FULL here on purpose: it rewrites the table
    and its TOAST under an ACCESS EXCLUSIVE lock, and a scrub of a few dozen
    rows does not need it.
    """
    with conn.cursor() as cur:
        cur.execute(f"SET lock_timeout = '{lock_timeout_ms}ms'")
        try:
            cur.execute(f"VACUUM (ANALYZE) {RUNS_TABLE}")
        finally:
            cur.execute("SET lock_timeout = 0")
    return "VACUUM (ANALYZE)"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help=f"full connection string (default: ${DSN_ENV})")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=54329)
    parser.add_argument("--user", default="paperclip")
    parser.add_argument("--dbname", default="paperclip")
    parser.add_argument(
        "--password-env",
        default=DEFAULT_PASSWORD_ENV,
        help=f"environment variable holding the password (default: {DEFAULT_PASSWORD_ENV})",
    )
    parser.add_argument(
        "--server-repo",
        default=os.environ.get(SERVER_REPO_ENV) or DEFAULT_SERVER_REPO,
        help=f"the paperclip checkout that carries the rule (default: ${SERVER_REPO_ENV} "
        f"or {DEFAULT_SERVER_REPO})",
    )
    parser.add_argument("--batch-size", type=int, default=25, help="rows per transaction")
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.2,
        help="pause between batches, so the instance keeps its share of the database",
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=300_000)
    parser.add_argument("--lock-timeout-ms", type=int, default=5_000)
    parser.add_argument("--max-batches", type=int, default=0, help="0 means no limit")
    parser.add_argument(
        "--verify-sample",
        type=int,
        default=25,
        help="live rows to compare the server's rule with the pinned detector on "
        "before writing (0 skips the check)",
    )
    parser.add_argument(
        "--no-post-scan",
        action="store_true",
        help="skip the scan that proves no bearer value is left behind",
    )
    parser.add_argument("--vacuum", action="store_true", help="VACUUM (ANALYZE) afterwards")
    parser.add_argument("--dry-run", action="store_true", help="count, do not write")
    parser.add_argument("--json-out", help="write the full report as JSON here")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    conninfo, connect_kwargs = resolve_connection(args, env)
    server_repo = Path(args.server_repo).expanduser()

    try:
        import psycopg
    except ImportError:
        print(
            "psycopg is not installed. Install it with: pip install 'psycopg[binary]'",
            file=sys.stderr,
        )
        return 2

    print("paperclip heartbeat_runs bearer scrub (DIG-5228)")
    print(f"  target: {redact_dsn(conninfo)}")
    print(f"  rule: {SERVER_REDACTION_SOURCE} ({SERVER_REDACTION_EXPORT})")
    print(f"  marker: {REDACTED_VALUE}")
    if args.dry_run:
        print("  mode: dry run, nothing is written")

    workdir = Path(tempfile.mkdtemp(prefix="paperclip-redact-"))
    rule = ServerRule(
        server_repo=server_repo,
        harness=Path(__file__).resolve().with_name(HARNESS_NAME),
        workdir=workdir,
    )
    try:
        rule.prepare()
    except RuleUnavailable as exc:
        print(f"refusing to write: {exc}", file=sys.stderr)
        shutil.rmtree(workdir, ignore_errors=True)
        return 1

    try:
        with psycopg.connect(conninfo, autocommit=True, **connect_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{args.statement_timeout_ms}ms'")

            fixture = check_fixture(rule)
            print(
                "  the server's rule and the pinned detector agree on the synthetic "
                f"fixture ({fixture['fixture_paths']} bearer cases, "
                f"{len(FIXTURE_ORDINARY_PATHS)} ordinary cases)"
            )

            sample = check_live_sample(conn, rule, args.verify_sample)
            print(
                "  the server's rule and the pinned detector agree on "
                f"{sample['compared']} live rows"
            )

            rows_in_table = count_rows(conn)
            result = run_scrub(conn, rule, args)

            values_left = None
            if not args.no_post_scan:
                values_left = count_values_left(conn)
                print(f"  after the scrub, bearer values left in the table: {values_left}")

            vacuum_statement = None
            if not args.dry_run and args.vacuum:
                vacuum_statement = run_vacuum(conn, lock_timeout_ms=args.lock_timeout_ms)
                print(f"  ran {vacuum_statement} {RUNS_TABLE}")

            report = {
                "target": redact_dsn(conninfo),
                "dry_run": bool(args.dry_run),
                "batch_size": args.batch_size,
                "rule": {
                    "source": SERVER_REDACTION_SOURCE,
                    "export": SERVER_REDACTION_EXPORT,
                    "marker": REDACTED_VALUE,
                    "server_repo": str(server_repo),
                },
                "check": {
                    "fixture_cases": fixture["fixture_paths"],
                    "live_rows_compared": sample["compared"],
                },
                "scan": {
                    "rows_in_table": rows_in_table,
                    "rows_scanned": result["rows_scanned"],
                    "rows_with_a_bearer_value": result["rows_with_a_bearer_value"],
                    "values_found": result["values_found"],
                    "values_inside_ttl": result["values_inside_ttl"],
                    "values_with_an_expiry_claim": result["values_with_an_expiry_claim"],
                },
                "scrub": {
                    "rows_rewritten": result["rows_rewritten"],
                    "rows_skipped": result["rows_skipped"],
                },
                "verify": {"values_left": values_left},
                "vacuum": vacuum_statement,
            }

            print("")
            print(
                f"  rows scanned: {result['rows_scanned']}, "
                f"rows with a bearer value: {result['rows_with_a_bearer_value']}, "
                f"values found: {result['values_found']}"
            )
            print(
                f"  values with an expiry claim: {result['values_with_an_expiry_claim']}, "
                f"still inside their own TTL: {result['values_inside_ttl']}, "
                f"rows rewritten: {result['rows_rewritten']}"
            )

            if args.json_out:
                with open(args.json_out, "w", encoding="utf-8") as handle:
                    json.dump(report, handle, indent=2, default=str)
                print(f"  wrote the report to {args.json_out}")
    except (RuleUnavailable, DriftError) as exc:
        print(f"refusing to write: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # The report is the point of the run: a failure must be loud and
        # named. The message names the failure, never a value.
        print(f"scrub failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        rule.close()
        shutil.rmtree(workdir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
