"""Migration 144 creates the digitrace index: four tenant-scoped tables and a
retention prune (DIG-2658, ADR-0036).

The index is the queryable window over the tracing data, not the record: R2
`digitrace-archive` is the system of record at 180 days, and these tables hold
90 days (scores 180, so a replay of an old window still has somewhere to write).

What this guard is for. Four properties are load-bearing and each has already
broken once somewhere in this schema's history:

* **Tenancy.** Every table carries ``workspace_id`` and RLS is enabled. The
  service-role paths bypass RLS, so the app-layer filter is the real boundary
  (the M6 finding); RLS here is the direct-client defence. A table added
  without RLS would be readable by any authenticated user.
* **No bodies.** ADR-0036 section 7: a span stores a hash and a length of its
  input/output, never the text. A ``prompt``/``completion`` column would put
  customer content in Postgres and outlive the 90-day index.
* **Retention.** The prune is SECURITY DEFINER with a pinned empty
  ``search_path`` and EXECUTE revoked, so it is not a PostgREST RPC, and it is
  additive-only so a re-apply is a no-op (the ledger is per filename, but a
  re-apply happens whenever someone runs the file by hand).
* **The MLflow exception stays out.** The ``mlflow`` schema needs role
  passwords; a password in a migration is a password in git.

Static parse only, matching the 141/143 guards. The schema this file assumes
(`public.workspaces`, `public.workspace_members`, the three Supabase roles,
`auth.uid()`) is migration 096/098, so this file cannot be applied alone and an
apply-level test belongs to the CHRIS STEP, not to a unit test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "prod" / "144_digitrace_index.sql"

TABLES = (
    "digitrace_traces",
    "digitrace_spans_index",
    "digitrace_scores",
    "digitrace_sessions",
)

# Columns that would put prompt or completion text in Postgres. ADR-0036
# section 7 forbids all of them; hash + length is the whole allowance.
FORBIDDEN_BODY_COLUMNS = (
    "prompt",
    "completion",
    "messages",
    "input_text",
    "output_text",
    "input_body",
    "output_body",
    "request_body",
    "response_body",
    "content",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS public\.{table}\s*\((.*?)\n\);",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match, f"CREATE TABLE IF NOT EXISTS public.{table} not found"
    return match.group(1)


def _columns(sql: str, table: str) -> list[str]:
    """Column names of a CREATE TABLE body, skipping constraint clauses."""
    names: list[str] = []
    for line in _table_body(sql, table).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if re.match(r"(CONSTRAINT|PRIMARY|UNIQUE|FOREIGN|CHECK)\b", stripped, re.I):
            continue
        match = re.match(r"([a-z_][a-z0-9_]*)\s+", stripped, re.I)
        if match:
            names.append(match.group(1).lower())
    return names


# ---------------------------------------------------------------------------
# The file is the only 144, and it parses
# ---------------------------------------------------------------------------


def test_migration_144_is_the_only_144() -> None:
    assert sorted(MIGRATIONS.rglob("144_*.sql")) == [MIGRATION]


def test_number_is_not_already_claimed_by_a_digitrace_object(sql: str) -> None:
    """No earlier migration creates a digitrace object, so there is no merge
    collision to reconcile and no second definition of these tables.

    Scoped to files numbered BELOW 144 on purpose. A later migration that
    merely mentions `digitrace_` (a follow-up that comments on these tables,
    or DIG-2661's read path) must not turn this guard red: it is a collision
    check on the number, not a claim on the word.
    """
    others = []
    for path in MIGRATIONS.rglob("*.sql"):
        if path == MIGRATION:
            continue
        prefix = path.name.split("_", 1)[0]
        if not prefix.isdigit() or int(prefix) >= 144:
            continue
        if "digitrace_" in path.read_text(encoding="utf-8", errors="replace"):
            others.append(path)
    assert others == [], f"digitrace objects already defined in: {others}"


def test_every_statement_parses_as_postgresql(sql: str) -> None:
    """The real parser, not a regex. Skipped where pglast is not installed."""
    pglast = pytest.importorskip("pglast")
    statements = pglast.parse_sql(sql)
    assert len(statements) > 10, "expected the four tables, indexes, policies and the prune"


# ---------------------------------------------------------------------------
# Shape: four public tables, all tenant-scoped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_table_is_additive_and_in_public(sql: str, table: str) -> None:
    assert f"public.{table}" in sql
    assert not re.search(rf"CREATE TABLE\s+public\.{table}", sql, re.I), (
        "use CREATE TABLE IF NOT EXISTS so a re-apply is a no-op"
    )


@pytest.mark.parametrize("table", TABLES)
def test_every_table_carries_the_house_tenancy_column(sql: str, table: str) -> None:
    """`workspace_id` is the key; a tenant slug is never the key."""
    body = _table_body(sql, table)
    assert re.search(
        r"workspace_id\s+uuid\s+NOT NULL\s+REFERENCES\s+public\.workspaces\s*\(\s*id\s*\)",
        body,
        re.I,
    ), f"{table} must carry workspace_id uuid NOT NULL REFERENCES public.workspaces(id)"


@pytest.mark.parametrize(
    "table", ("digitrace_traces", "digitrace_spans_index", "digitrace_sessions")
)
def test_edge_values_are_not_columns_on_the_index_rows(sql: str, table: str) -> None:
    """ADR-0036 section 5, in as many words: `tenant_slug` and
    `tenant_slug_verified` are edge values and "are not columns on the index
    rows". The archive object carries them; the index's one tenancy column is
    `workspace_id`.

    This is a guard against the shape that broke the first draft: a column the
    writer never populates reads NULL/false on every row, so the flag says
    "unverified" even for a claim that resolved. A wrong value with a
    diagnostic's name is worse than no column.
    """
    columns = _columns(sql, table)
    assert "tenant_slug" not in columns, f"{table} must not carry tenant_slug (ADR-0036 §5)"
    assert "tenant_slug_verified" not in columns, (
        f"{table} must not carry tenant_slug_verified (ADR-0036 §5)"
    )


def test_tenancy_has_exactly_one_column_and_the_archive_carries_the_edge_values(raw: str) -> None:
    """The decision is recorded where the next reader looks: in the header."""
    assert re.search(r"EDGE VALUES", raw), "the header must say what the ADR says"
    assert re.search(r"NOT stored on the index row at all", raw)


def test_sessions_table_comment_names_its_writer(sql: str) -> None:
    """The reviewer's B2 on a8705ad13c: the table shipped with rolled-up
    counters, no way to maintain them, and a COMMENT that claimed them. The
    table's own inventory entry now names the function that maintains it, so
    the next reader is not told totals exist without being told who writes
    them.
    """
    match = re.search(r"COMMENT ON TABLE public\.digitrace_sessions IS", sql, re.I)
    assert match, "the sessions table must carry an inventory comment"
    # The comment body itself contains a ';', so the statement is not
    # delimited that way: read the literal block that follows the entry.
    body = sql[match.end() : match.end() + 700]
    assert "refresh_digitrace_session" in body, "the comment must name the writer"
    assert re.search(r"PostgREST upsert", body, re.I), (
        "and must say why a plain upsert cannot be the writer"
    )


def test_no_prompt_or_completion_text_anywhere(sql: str) -> None:
    """ADR-0036 section 7. Bodies live in R2; this index holds hashes."""
    for table in TABLES:
        columns = _columns(sql, table)
        for forbidden in FORBIDDEN_BODY_COLUMNS:
            assert forbidden not in columns, (
                f"{table}.{forbidden} would store body text in Postgres; "
                "store a hash and a length instead"
            )


def test_spans_store_hash_and_length_not_text(sql: str) -> None:
    columns = _columns(sql, "digitrace_spans_index")
    for expected in ("input_hash", "input_length", "output_hash", "output_length"):
        assert expected in columns, f"digitrace_spans_index.{expected} missing"


def test_jsonb_blobs_are_defaulted_not_nullable(sql: str) -> None:
    """attributes/resource are allowlisted projections, never a null dump."""
    for table in ("digitrace_traces", "digitrace_spans_index"):
        body = _table_body(sql, table)
        assert re.search(r"attributes\s+jsonb\s+NOT NULL\s+DEFAULT\s+'\{\}'::jsonb", body, re.I), (
            f"{table}.attributes must default to an empty object"
        )


# ---------------------------------------------------------------------------
# RLS and grants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", TABLES)
def test_rls_is_enabled_on_every_table(sql: str, table: str) -> None:
    assert re.search(rf"ALTER TABLE public\.{table} ENABLE ROW LEVEL SECURITY", sql, re.I), (
        f"{table} would be world-readable to any authenticated user without RLS"
    )


@pytest.mark.parametrize("table", TABLES)
def test_anon_holds_nothing(sql: str, table: str) -> None:
    """These are tenant rows. anon must never be granted anything, ever."""
    assert re.search(
        rf"REVOKE ALL ON public\.{table} FROM PUBLIC, anon, authenticated;", sql, re.I
    ), f"{table} must revoke authenticated explicitly, not rely on 060's default ACL"
    assert not re.search(
        rf"GRANT\s+\w[\w,\s]*ON public\.{table}\s+TO\s+[^;]*\banon\b", sql, re.I
    ), f"{table} must not be granted to anon"


@pytest.mark.parametrize("table", TABLES)
def test_authenticated_can_read_but_not_write(sql: str, table: str) -> None:
    """A direct client read is fine; ingest is service_role only."""
    assert re.search(rf"GRANT SELECT ON public\.{table} TO authenticated;", sql, re.I)
    assert not re.search(
        rf"GRANT\s+[^;]*\b(INSERT|UPDATE|DELETE)\b[^;]*ON public\.{table}\s+TO\s+authenticated",
        sql,
        re.I,
    ), f"{table} must not give authenticated a write path"


@pytest.mark.parametrize("table", TABLES)
def test_house_select_policy_is_used_verbatim(sql: str, table: str) -> None:
    """The migration-098 policy: name, shape and membership predicate."""
    assert re.search(
        rf'DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public\.{table};',
        sql,
        re.I,
    ), "replay-safe idiom: the DROP immediately precedes the CREATE"
    policy = re.search(
        rf'CREATE POLICY "authenticated_select_own_workspace" ON public\.{table}\s+'
        r"FOR SELECT TO authenticated\s+USING\s*\((.*?)\);",
        sql,
        re.I | re.S,
    )
    assert policy, f"{table} must carry the house SELECT policy"
    body = policy.group(1)
    assert re.search(
        r"workspace_id IN \(\s*SELECT workspace_id FROM public\.workspace_members", body, re.I
    )
    assert re.search(r"user_id = auth\.uid\(\)", body, re.I)


def test_service_role_holds_read_and_write(sql: str) -> None:
    for table in TABLES:
        assert re.search(
            rf"GRANT SELECT, INSERT, UPDATE, DELETE ON public\.{table} TO service_role;",
            sql,
            re.I,
        ), table


def test_tenant_boundary_is_documented_as_the_app_filter(raw: str) -> None:
    """The M6 finding: service_role bypasses RLS, so RLS is not the boundary.

    Read with comments intact - this is a header statement, and the next seat
    to touch the file needs it where they will actually read it.
    """
    assert re.search(r"service_role.{0,80}BYPASSRLS", raw, re.I | re.S)
    assert re.search(r"APPLICATION-LAYER TENANT FILTER", raw, re.I)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_sessions_writer_recomputes_from_the_spans_index(sql: str) -> None:
    """Recompute, not accumulate. The consumer reads from a Queue, which is
    at-least-once: adding a batch's deltas double-counts on a redelivery, while
    recomputing from `digitrace_spans_index` lands on the same numbers twice.
    """
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.refresh_digitrace_session") :]
    fn = fn[: fn.index("$$;")]
    assert re.search(
        r"CREATE OR REPLACE FUNCTION public\.refresh_digitrace_session\(\s*"
        r"p_workspace_id uuid,\s*p_session_id text\s*\)",
        fn,
    ), "the writer takes the two tenancy keys and nothing else"
    assert re.search(r"count\(DISTINCT s\.trace_id\)", fn, re.I), "trace_count"
    assert re.search(r"count\(\*\)", fn, re.I), "span_count"
    assert re.search(r"sum\(s\.total_tokens\)", fn, re.I)
    assert re.search(r"sum\(s\.cost_usd\)", fn, re.I)
    assert re.search(r"ON CONFLICT \(workspace_id, session_id\) DO UPDATE", fn, re.I)
    # the counters are SET from the recomputation, never `+ excluded.`
    assert not re.search(r"trace_count\s*=\s*digitrace_sessions\.trace_count", fn, re.I), (
        "accumulating would double-count on a Queue redelivery"
    )


def test_sessions_writer_is_locked_down_and_pins_its_path(sql: str) -> None:
    """INVOKER, not DEFINER: the only grantee already holds the DML and the
    SELECT, so definer rights would add an escalation surface for nothing."""
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.refresh_digitrace_session") :]
    fn = fn[: fn.index("$$;")]
    assert re.search(r"SET search_path = ''", fn)
    assert re.search(r"SECURITY INVOKER", fn), "say it explicitly, do not rely on the default"
    assert not re.search(r"SECURITY DEFINER", fn), "no definer rights are needed here"
    for grant in (
        r"REVOKE ALL ON FUNCTION public\.refresh_digitrace_session\(uuid, text\) FROM PUBLIC;",
        r"REVOKE ALL ON FUNCTION public\.refresh_digitrace_session\(uuid, text\) FROM anon, authenticated;",
        r"GRANT EXECUTE ON FUNCTION public\.refresh_digitrace_session\(uuid, text\) TO service_role;",
    ):
        assert re.search(grant, sql, re.I), grant


def test_sessions_writer_serialises_concurrent_refreshes(sql: str) -> None:
    """Recompute is idempotent, not concurrency-safe. Two overlapping calls
    each read the spans before either writes, and the later writer can store
    the older total - an undercount that never corrects itself. The function
    takes a transaction-scoped advisory lock on the session before it reads.
    """
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.refresh_digitrace_session") :]
    fn = fn[: fn.index("$$;")]
    lock = re.search(
        r"pg_catalog\.pg_advisory_xact_lock\(\s*"
        r"pg_catalog\.hashtextextended\(p_workspace_id::text \|\| ':' \|\| p_session_id, 0\)\s*\)",
        fn,
    )
    assert lock, "the refresh must serialise on (workspace_id, session_id) before it reads"
    # ...and before the aggregate, or it protects nothing.
    assert fn.index("pg_advisory_xact_lock") < fn.index("FROM public.digitrace_spans_index"), (
        "the lock must be taken before the recompute, not after it"
    )


def test_sessions_token_total_is_wide_enough_for_a_bigint_sum(sql: str) -> None:
    """The reviewer's note: `sum(total_tokens)` is bigint, so an int4 column
    raises `integer out of range` above 2 147 483 647 instead of storing it.
    No rows exist yet, so widening is free now and never free later.
    """
    columns = _columns(sql, "digitrace_sessions")
    assert "total_tokens" in columns
    assert re.search(
        r"total_tokens\s+bigint\s+NOT NULL DEFAULT 0", _table_body(sql, "digitrace_sessions")
    ), "total_tokens must be bigint to receive a bigint sum"


def test_apply_section_stops_on_an_already_applied_ledger(raw: str) -> None:
    """#6525 edits a migration that already merged. Re-running it against an
    applied database is a silent no-op (CREATE TABLE IF NOT EXISTS keeps the old
    columns), so the file itself has to say stop and go through 145 instead.
    """
    assert re.search(r"already carries 144,\s*\n?--\s*STOP", raw, re.I), (
        "the Apply section must stop the operator when the ledger already has 144"
    )
    assert "SILENT NO-OP" in raw.upper()
    assert re.search(r"\b145\b", raw), "and must name the migration that would carry the fix"


def test_sessions_writer_does_not_invent_an_empty_row(sql: str) -> None:
    """A call for a session with no spans written yet must not create a row
    full of zeroes that later reads as a real, empty session."""
    fn = sql[sql.index("CREATE OR REPLACE FUNCTION public.refresh_digitrace_session") :]
    fn = fn[: fn.index("$$;")]
    assert re.search(r"IF v_spans = 0 THEN\s+RETURN;", fn, re.I)


def test_retention_function_signature_and_defaults(sql: str) -> None:
    assert re.search(
        r"CREATE OR REPLACE FUNCTION public\.prune_digitrace_index\(\s*"
        r"index_retain_days integer DEFAULT 90,\s*"
        r"scores_retain_days integer DEFAULT 180\s*\)",
        sql,
        re.I,
    )


def test_retention_function_is_locked_down(sql: str) -> None:
    """SECURITY DEFINER + empty search_path + no EXECUTE for the bundled keys."""
    assert re.search(r"SECURITY DEFINER", sql, re.I)
    assert re.search(r"SET search_path = ''", sql, re.I)
    assert re.search(
        r"REVOKE ALL ON FUNCTION public\.prune_digitrace_index\(integer, integer\) FROM PUBLIC;",
        sql,
        re.I,
    )
    assert re.search(
        r"REVOKE ALL ON FUNCTION public\.prune_digitrace_index\(integer, integer\) FROM anon, authenticated;",
        sql,
        re.I,
    )


def test_retention_arguments_are_validated_before_use(sql: str) -> None:
    """The only injection surface is two integers; both are range-checked."""
    assert re.search(r"index_retain_days IS NULL OR index_retain_days < 1", sql, re.I)
    assert re.search(r"scores_retain_days IS NULL OR scores_retain_days < 1", sql, re.I)
    assert sql.count("RAISE EXCEPTION") >= 3, "two argument guards plus the owner assertion"


def test_retention_keeps_the_measured_window(sql: str) -> None:
    """90 days of index, 180 days of scores - the ADR-0036 numbers."""
    prune = sql[sql.index("CREATE OR REPLACE FUNCTION public.prune_digitrace_index") :]
    assert re.search(r"started_at < index_cutoff", prune, re.I)
    assert re.search(r"created_at < scores_cutoff", prune, re.I)
    assert not re.search(r"TRUNCATE", sql, re.I)


def test_sessions_are_pruned_on_last_activity_not_start(sql: str) -> None:
    """A live session must never be pruned under the consumer's feet."""
    assert re.search(
        r"DELETE FROM public\.digitrace_sessions\s+WHERE COALESCE\(last_activity_at, started_at, created_at\) < index_cutoff",
        sql,
        re.I,
    )


def test_scores_outlive_the_index(sql: str) -> None:
    """A replay of a 91-180 day window still needs somewhere to write scores."""
    assert re.search(r"scores_retain_days integer DEFAULT 180", sql, re.I)
    prune = sql[sql.index("CREATE OR REPLACE FUNCTION public.prune_digitrace_index") :]
    scores_cutoff = re.search(
        r"DELETE FROM public\.digitrace_scores WHERE (\w+) < scores_cutoff", prune, re.I
    )
    assert scores_cutoff, "scores are pruned against the scores cutoff, not the index cutoff"


def test_apply_fails_loudly_when_the_applier_is_not_the_owner(sql: str) -> None:
    """Migration 061's lesson: a wrong-role install prunes 0 rows, silently."""
    assert re.search(r"pg_has_role\(current_user, c\.relowner, 'USAGE'\)", sql, re.I)
    assert re.search(r"RAISE EXCEPTION", sql, re.I)


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------


def test_schedule_is_guarded_and_idempotent(sql: str) -> None:
    assert re.search(r"WHERE extname = 'pg_cron'", sql, re.I), (
        "an absent pg_cron would otherwise roll back the whole migration"
    )
    assert re.search(r"RETURN;", sql, re.I)
    assert re.search(r"cron\.schedule", sql, re.I)
    for job in ("digitrace-index-prune", "digitrace-index-vacuum"):
        assert job in sql


def test_scheduled_prune_uses_the_measured_window(sql: str) -> None:
    assert re.search(r"'SELECT public\.prune_digitrace_index\(90, 180\);'", sql, re.I)


def test_vacuum_is_plain_analyze_and_never_full(sql: str) -> None:
    assert re.search(r"VACUUM \(ANALYZE\)", sql, re.I)
    assert not re.search(r"VACUUM FULL", sql, re.I), (
        "ACCESS EXCLUSIVE lock, and no bloat to reclaim"
    )


def test_no_top_level_vacuum_statement(sql: str) -> None:
    """VACUUM is illegal inside a transaction block; the migrate path wraps it."""
    for line in sql.splitlines():
        assert not re.match(r"\s*VACUUM\b", line, re.I), (
            f"VACUUM cannot run inside the apply transaction: {line.strip()!r}"
        )


# ---------------------------------------------------------------------------
# Scope: additive only, and the MLflow exception stays out
# ---------------------------------------------------------------------------


def test_migration_is_additive_only(sql: str) -> None:
    for forbidden in (r"DROP TABLE", r"TRUNCATE", r"ALTER TABLE public\.(?!digitrace_)"):
        assert not re.search(forbidden, sql, re.I), forbidden
    # The one allowed DROP is the replay-safe policy reset.
    drops = re.findall(r"DROP\s+(\w+(?:\s+\w+)?)", sql, re.I)
    assert {d.split()[0].upper() for d in drops} == {"POLICY"}, drops
    assert len(re.findall(r"DROP POLICY IF EXISTS", sql, re.I)) == len(TABLES)


def test_mlflow_exception_is_not_in_this_migration(sql: str) -> None:
    """The dedicated schema needs role passwords: a CHRIS STEP, never git."""
    assert not re.search(r"CREATE SCHEMA", sql, re.I)
    assert not re.search(r"CREATE ROLE", sql, re.I)
    assert not re.search(r"\bPASSWORD\b", sql, re.I)
    assert not re.search(r"GRANT\s+.*ON SCHEMA mlflow", sql, re.I)


def test_no_connection_or_extension_is_opened(sql: str) -> None:
    """The M3 finding: this file opens zero connections, and needs no extension
    of its own (gen_random_uuid is core since PostgreSQL 13)."""
    assert not re.search(r"CREATE EXTENSION", sql, re.I)
    assert not re.search(r"dblink|postgres_fdw|http_", sql, re.I)


def test_indexes_are_not_redundant_with_the_unique_keys(sql: str) -> None:
    """A (workspace_id, trace_id) btree is dead weight: the unique keys on
    spans and scores already lead with those two columns."""
    for index in re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)", sql, re.I):
        assert index not in (
            "digitrace_spans_index_workspace_trace_idx",
            "digitrace_scores_workspace_trace_idx",
        ), f"{index} duplicates the prefix of a unique constraint"
