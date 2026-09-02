"""Unit tests for migration 061 (LangGraph checkpointer retention, #1758).

Hermetic pure-SQL parse checks in the ``test_migration_051.py`` mold: no
Postgres, no network.

The load-bearing guarantees, in order of how expensive they are to get wrong:

1. **No ``VACUUM`` in the migration body.** ``db-migrate.yml`` applies unwrapped
   migrations with ``--single-transaction``, and ``VACUUM`` cannot run inside a
   transaction block — one would abort and roll the whole migration back.
2. **The file must not look self-wrapping to the deploy script.** That script
   branches on ``grep -qiE '(^|[[:space:]])begin[[:space:]]*;'`` and skips
   ``--single-transaction`` when it matches; this test binds to that exact
   regex, so a stray ``BEGIN;`` cannot silently change how prod applies it.
3. **``VACUUM FULL`` is forbidden** (user ruling D6) — it takes an ACCESS
   EXCLUSIVE lock and these insert-only tables carry no bloat to reclaim.
4. **Retention is never zero** and pruning is **thread-scoped** —
   ``checkpoint_blobs`` has no ``checkpoint_id``, so a per-checkpoint delete
   would orphan blobs, and ``resume_run_id`` makes recent threads load-bearing.
5. **The prune is not reachable as a PostgREST RPC** by the anon key that ships
   in the digiquant.io bundle.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "061_checkpointer_retention.sql"
)

# The three tables the prune must cover. `checkpoint_migrations` is LangGraph's own
# schema-version table and is deliberately excluded.
PRUNED_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs")

RETAIN_DAYS = 14

# Verbatim from .github/workflows/db-migrate.yml: a match makes the deploy script
# run the file WITHOUT --single-transaction.
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def statements(sql: str) -> str:
    """The migration with comment lines stripped, so assertions bind to executable SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_no_vacuum_in_the_migration_body(statements: str) -> None:
    """VACUUM inside --single-transaction aborts and rolls the migration back.

    It is legal only inside the pg_cron command string, which pg_cron runs as a
    bare statement outside an explicit transaction.
    """
    # Split on the string-literal delimiter: even segments are outside quotes, odd
    # segments inside. (An escaped '' yields an empty even segment, which is inert.)
    segments = statements.split("'")
    outside_literals = "".join(segments[::2])
    inside_literals = "".join(segments[1::2])
    assert not re.search(r"\bVACUUM\b", outside_literals, re.I), (
        "VACUUM must never be an executable statement in a migration applied with "
        "--single-transaction; it belongs only inside the cron.schedule command string"
    )
    assert re.search(r"\bVACUUM\b", inside_literals, re.I), "expected a scheduled VACUUM"


def test_file_is_not_self_wrapping(sql: str) -> None:
    """db-migrate.yml drops --single-transaction when this regex matches."""
    assert not SELF_WRAP_REGEX.search(sql), (
        "a bare BEGIN; makes db-migrate.yml apply this file non-atomically"
    )


def test_never_vacuum_full(statements: str) -> None:
    # Ruling D6: ACCESS EXCLUSIVE lock, and zero bloat to reclaim so it would buy
    # nothing. The header comment explains the exclusion, hence executable-SQL only.
    assert not re.search(r"VACUUM\s+FULL", statements, re.I)


def test_vacuum_job_is_plain_analyze_over_all_three_tables(statements: str) -> None:
    match = re.search(r"VACUUM \(ANALYZE\)([^;]*);", statements, re.I)
    assert match, "expected a plain VACUUM (ANALYZE) in the scheduled command"
    for table in PRUNED_TABLES:
        assert f"public.{table}" in match.group(1), f"{table} missing from the VACUUM list"


def test_prune_function_is_created_idempotently(statements: str) -> None:
    assert re.search(
        r"CREATE OR REPLACE FUNCTION public\.prune_langgraph_checkpoints\(\s*"
        r"retain_days integer DEFAULT 14\s*\)",
        statements,
    ), "prune function must be CREATE OR REPLACE and default to the 14-day ruling"


def test_retention_window_is_fourteen_days(statements: str) -> None:
    """D6 ruling. Both the function default and the scheduled call must say 14."""
    assert re.search(rf"prune_langgraph_checkpoints\({RETAIN_DAYS}\)", statements), (
        "the cron job must pass the retention window explicitly so it is visible in cron.job"
    )


def test_retention_cannot_be_zero_or_negative(statements: str) -> None:
    """`resume_run_id` resumes a prior run's thread, so recent threads are load-bearing."""
    assert re.search(
        r"IF retain_days IS NULL OR retain_days < 1 THEN\s+RAISE EXCEPTION",
        statements,
    ), "missing the retain_days >= 1 guard"


def test_staleness_is_keyed_on_the_newest_checkpoint_per_thread(statements: str) -> None:
    """max() per thread, so an in-flight run is never eligible even at retain_days=1."""
    assert re.search(r"HAVING max\(\(c\.checkpoint ->> 'ts'\)::timestamptz\)\s*<", statements), (
        "staleness must be max((checkpoint->>'ts')::timestamptz) grouped per thread"
    )
    assert re.search(r"GROUP BY c\.thread_id", statements)


@pytest.mark.parametrize("table", PRUNED_TABLES)
def test_prune_is_thread_scoped_across_all_three_tables(statements: str, table: str) -> None:
    # checkpoint_blobs is keyed (thread_id, checkpoint_ns, channel, version) with no
    # checkpoint_id, so anything narrower than thread_id orphans blobs.
    assert re.search(
        rf"DELETE FROM public\.{table} \w+ WHERE \w+\.thread_id = ANY \(stale_threads\);",
        statements,
    ), f"missing thread-scoped delete for {table}"


def test_checkpoint_migrations_is_never_touched(statements: str) -> None:
    """LangGraph's own schema-version table — emptying it re-runs its setup migrations.

    Checked outside string literals so a future clarifying `COMMENT ON TABLE` body may
    name the table without failing this test; what must never appear is a reference to
    it in executable position.
    """
    outside_literals = "".join(statements.split("'")[::2])
    assert "checkpoint_migrations" not in outside_literals


def test_prune_is_not_exposed_to_anon(statements: str) -> None:
    """PostgREST would otherwise publish it as rpc/prune_langgraph_checkpoints."""
    signature = r"FUNCTION public\.prune_langgraph_checkpoints\(integer\)"
    assert re.search(rf"REVOKE ALL ON {signature} FROM PUBLIC;", statements)
    assert re.search(rf"REVOKE ALL ON {signature} FROM anon, authenticated;", statements)


def test_definer_function_pins_search_path(statements: str) -> None:
    # SECURITY DEFINER without a pinned search_path is a privilege-escalation vector.
    assert "SECURITY DEFINER" in statements
    assert re.search(r"SET search_path = ''", statements)


def test_install_asserts_table_ownership(statements: str) -> None:
    """A non-owner install prunes 0 rows and skips the VACUUM, both silently."""
    assert "pg_has_role(current_user" in statements
    assert re.search(r"RAISE EXCEPTION\s*\n?\s*'migration 061:", statements)


def test_schedule_is_guarded_on_pg_cron_presence(statements: str) -> None:
    """A stack without pg_cron must not roll the whole migration back."""
    assert re.search(
        r"IF NOT EXISTS \(SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'\)", statements
    )


def test_both_cron_jobs_are_scheduled_by_name(statements: str) -> None:
    """cron.schedule upserts by (username, jobname) since pg_cron 1.4 — idempotent replay."""
    for jobname in ("langgraph-checkpoint-prune", "langgraph-checkpoint-vacuum"):
        assert re.search(rf"cron\.schedule\(\s*'{jobname}'", statements), (
            f"missing cron.schedule for {jobname}"
        )


def test_cron_slots_avoid_the_olympus_and_prices_windows(statements: str) -> None:
    """Olympus is 12:00 UTC (+4h); prices-live pg_cron fires 13:00-01:00 UTC."""
    schedules = re.findall(r"cron\.schedule\(\s*'[\w-]+',\s*'([^']+)'", statements)
    assert len(schedules) == 2, f"expected two schedules, got {schedules}"
    for spec in schedules:
        minute, hour, rest = spec.split(" ", 2)
        assert hour == "5", f"{spec!r} must run in the 05:00 UTC hour"
        assert minute.isdigit(), f"{spec!r} must fire once, not on a step/range"
        assert rest == "* * *", f"{spec!r} must run every day"
    prune_at, vacuum_at = (int(spec.split(" ", 1)[0]) for spec in schedules)
    assert prune_at < vacuum_at, "the VACUUM must be scheduled after the prune"


def test_nothing_destructive_beyond_the_scoped_deletes(statements: str) -> None:
    assert not re.search(r"\bDROP TABLE\b|\bTRUNCATE\b|\bDROP FUNCTION\b", statements, re.I)
    assert not re.search(r"\bGRANT\b", statements, re.I), "retention must not grant anything"
    # Every DELETE must be thread-scoped; an unqualified one would empty the tables.
    for delete in re.findall(r"DELETE FROM[^;]*;", statements, re.I):
        assert "thread_id = ANY (stale_threads)" in delete, f"unscoped delete: {delete!r}"


def test_migration_does_not_prune_at_apply_time(statements: str) -> None:
    """061 is structural: the first cron fire does the work, so a replay is a no-op."""
    assert not re.search(
        r"^\s*(SELECT|PERFORM)\s+public\.prune_langgraph_checkpoints",
        statements,
        re.I | re.MULTILINE,
    ), "the prune must only be invoked from the cron job, not inline"


def test_tables_are_documented(statements: str) -> None:
    # obj_description was NULL on all three before this migration.
    for table in PRUNED_TABLES:
        assert re.search(rf"COMMENT ON TABLE public\.{table} IS", statements)
    assert re.search(
        r"COMMENT ON FUNCTION public\.prune_langgraph_checkpoints\(integer\) IS", statements
    )


def test_documented_in_schema_and_architecture() -> None:
    """An operator must be able to find the window, the job names and the pause commands.

    Deliberately coupled: `digiquant/supabase/SCHEMA.md` is edited by several packages in
    this wave, so a rebase that drops the retention section should fail loudly here rather
    than leave a recurring production DELETE undocumented. Anchors are the unambiguous
    identifiers, not the bare migration number.
    """
    schema_md = (REPO_ROOT / "digiquant" / "supabase" / "SCHEMA.md").read_text(encoding="utf-8")
    for anchor in (
        "langgraph-checkpoint-prune",
        "langgraph-checkpoint-vacuum",
        "prune_langgraph_checkpoints",
        "cron.unschedule",
    ):
        assert anchor in schema_md, f"SCHEMA.md lost the retention anchor {anchor!r}"

    arch_md = (REPO_ROOT / "digigraph" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "prune_langgraph_checkpoints" in arch_md
