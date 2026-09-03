"""Unit tests for migration 064 — ``public.prices_live_lease`` and the atomic claim (#1756).

Hermetic pure-SQL parse checks in the ``test_migration_060.py`` / ``test_migration_061.py`` /
``test_migration_063.py`` mold: no Postgres, no network.

WHAT THIS MIGRATION IS FOR
--------------------------
``prices-live`` polls Finnhub's free tier (60 calls/min) for up to ``MAX_SYMBOLS = 40`` symbols
and upserts ``public.prices_live``. ``verify_jwt: true`` is not authorization — the anon key
ships in plaintext in every digiquant.io bundle — so anyone can invoke the function and burn
the quota out from under the 60 s pg_cron job. #1756 first answered that with a shared secret
in an ``x-prices-live-secret`` header. That secret is withdrawn: it is an operational
credential to store, rotate and lose, and it bounded *who* invoked rather than *how often* a
fetch happens. This migration bounds the rate instead, which is the quantity that was actually
unbounded.

WHY THE CLAIM MUST BE ONE ``UPDATE`` — READ BEFORE "SIMPLIFYING" IT
------------------------------------------------------------------
The obvious guard, ``SELECT max(updated_at) FROM prices_live`` plus a freshness comparison, is
READ-THEN-ACT and protects nothing. ``updated_at`` is written by the upsert AFTER the fetch
loop, and that loop is 40 symbols × 150 ms of deliberate stagger — about SIX SECONDS. Every
invocation arriving inside that window reads the same stale timestamp, all pass, all fetch: ten
parallel requests is ~400 Finnhub calls in six seconds. Advisory locks do not substitute
either, because PostgREST hands out a fresh session per RPC call and a session-scoped lock
would release long before the six-second fetch it needs to cover.

One conditional ``UPDATE ... WHERE claimed_at < <cutoff>`` has no such gap. Concurrent callers
block on the lease row's lock, then re-evaluate the ``WHERE`` clause against the committed new
``claimed_at`` under READ COMMITTED and match zero rows. ``FOUND`` tells each caller whether it
won. Exactly one winner per window, whatever the arrival pattern.
``test_the_claim_is_one_conditional_update`` and ``test_the_claim_never_reads_before_it_writes``
are the two assertions that keep that shape; everything else here is the access control that
makes the shape matter.

THE REVOKE IS LOAD-BEARING IN BOTH DIRECTIONS
---------------------------------------------
Revoking EXECUTE from ``anon``/``authenticated`` is not tidiness. Without it an attacker calls
``claim_prices_live_refresh`` directly in a loop, wins every window, and leaves the legitimate
cron nothing to claim — a denial of *freshness*, the mirror image of the quota attack the lease
exists to stop. ``test_no_client_role_may_execute_the_claim`` is the security assertion of this
module.

``pytestmark = pytest.mark.unit`` is mandatory, not decorative. The lane that collects this
directory is ``test-research-graph.yml`` (``pytest -m unit tests/dq/research/ …``); the plain
``digiquant tests`` job installs only ``digiquant[dev]``, so digigraph is absent and
``tests/dq/research/conftest.py`` ignores the whole directory there. An unmarked file is not an
error, it is silently deselected — it would run in no lane at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "064_prices_live_lease.sql"

TABLE = "public.prices_live_lease"
FUNCTION = "public.claim_prices_live_refresh"
ARG = "min_age_seconds"

# Verbatim from .github/workflows/db-migrate.yml:
#     grep -qiE '(^|[[:space:]])begin[[:space:]]*;'
# A match makes the deploy script apply the file WITHOUT --single-transaction. Note it is the
# trailing semicolon that matters: a plpgsql `BEGIN` opening a function body is followed by a
# statement, never by `;`, so the claim function does not trip this.
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

# PUBLIC is the entry that is easy to forget: naming only anon and authenticated leaves
# untouched the privilege both of them inherit through PUBLIC. For a FUNCTION that default is
# not hypothetical — Postgres grants EXECUTE to PUBLIC on every new function automatically.
REVOKED_ROLES = ("PUBLIC", "anon", "authenticated")

CLIENT_ROLES = ("public", "anon", "authenticated")

# `ON public.prices_live_lease`, with the optional `TABLE` keyword. Written as a fragment so
# the same target can be spliced into the REVOKE and GRANT patterns.
TABLE_TARGET = rf"ON\s+(?:TABLE\s+)?{re.escape(TABLE)}\b"
# The function's identity args are part of its name in a GRANT/REVOKE — `(integer)` must be
# there or the statement fails to resolve once an overload ever exists.
FUNCTION_TARGET = rf"ON\s+FUNCTION\s+{re.escape(FUNCTION)}\s*\(\s*integer\s*\)"


def _strip_sql_comments(sql: str) -> str:
    """Drop whole-line ``--`` comments so assertions bind to executable SQL.

    Duplicated from ``test_migration_063.py`` rather than imported: nothing in this repo
    imports across test modules, and doing so would make these assertions depend on
    rootdir/pythonpath resolution.
    """
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _strip_sql_literals(sql: str) -> str:
    """Blank out single-quoted string literals, for statement counting only.

    ``RAISE EXCEPTION ... USING HINT`` messages in this file are expected to talk about the
    very statements being counted ("ONE conditional UPDATE", "never SELECT then UPDATE"), and a
    naive ``sql.count("UPDATE")`` would read those as extra statements. Never use this for the
    positive assertions — it also eats ``DEFAULT '-infinity'`` and ``search_path = ''``.
    """
    return re.sub(r"'(?:''|[^'])*'", "''", sql, flags=re.DOTALL)


@pytest.fixture(scope="module")
def raw() -> str:
    """The file exactly as ``db-migrate.yml`` greps it — comments and all."""
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    """The migration with comment lines stripped, so assertions bind to executable SQL."""
    return _strip_sql_comments(raw)


@pytest.fixture(scope="module")
def table_body(sql: str) -> str:
    """The parenthesised column list of the lease table's ``CREATE TABLE``.

    Scoped to the statement on purpose: any ``COMMENT ON COLUMN`` prose further down survives
    comment stripping, and a whole-file grep for ``NOT NULL`` would be satisfied by a sentence
    describing the constraint rather than by the constraint.
    """
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(TABLE)}\s*\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"no CREATE TABLE for {TABLE}"
    return match.group("body")


@pytest.fixture(scope="module")
def columns(table_body: str) -> dict[str, str]:
    """``claimed_at`` → the rest of its definition line, from ``CREATE TABLE`` only."""
    out: dict[str, str] = {}
    for line in table_body.splitlines():
        definition = line.strip().rstrip(",").strip()
        if not definition or definition.upper().startswith(("CONSTRAINT", "CHECK", "PRIMARY")):
            continue
        name, _, rest = definition.partition(" ")
        out[name.lower()] = " ".join(rest.split())
    return out


@pytest.fixture(scope="module")
def function_body(sql: str) -> str:
    """The dollar-quoted body of ``claim_prices_live_refresh``.

    The tag is captured rather than assumed so a ``$function$`` quote reads the same as ``$$``.
    """
    match = re.search(
        r"AS\s+\$(?P<tag>\w*)\$(?P<body>.*?)\$(?P=tag)\$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"no dollar-quoted body for {FUNCTION}"
    return match.group("body")


@pytest.fixture(scope="module")
def create_function(sql: str) -> str:
    """The ``CREATE OR REPLACE FUNCTION`` header, up to the start of the dollar-quoted body."""
    match = re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{re.escape(FUNCTION)}\s*\((?P<header>.*?)AS\s+\$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, (
        f"no `CREATE OR REPLACE FUNCTION {FUNCTION}` — plain CREATE FUNCTION raises 42723 on "
        "the second application and db-migrate.yml re-applies any file whose ledger row is "
        "missing"
    )
    return match.group("header")


def _statements(sql: str, pattern: str) -> list[str]:
    """Every ``;``-terminated statement matching ``pattern``, literals left intact."""
    return [m.group(0) for m in re.finditer(rf"{pattern}[^;]*;", sql, re.IGNORECASE | re.DOTALL)]


def _roles(statement: str, keyword: str) -> set[str]:
    match = re.search(rf"\b{keyword}\b(?P<roles>[^;]*)", statement, re.IGNORECASE)
    assert match, f"statement has no {keyword} clause: {statement}"
    return {
        role.strip().strip('"').lower() for role in match.group("roles").split(",") if role.strip()
    }


@pytest.fixture(scope="module")
def table_revokes(sql: str) -> list[str]:
    found = _statements(sql, rf"REVOKE\s+[^;]*?{TABLE_TARGET}")
    assert found, (
        f"no REVOKE on {TABLE}. RLS with zero policies is the primary control, but the table "
        "privileges underneath it are the defense in depth migrations 050/052/057/060/063 "
        "established, and a future re-widening of the schema grants would otherwise land here"
    )
    return found


@pytest.fixture(scope="module")
def function_revokes(sql: str) -> list[str]:
    found = _statements(sql, rf"REVOKE\s+[^;]*?{FUNCTION_TARGET}")
    assert found, (
        f"no REVOKE on {FUNCTION}(integer). Postgres grants EXECUTE to PUBLIC on every new "
        "function by default, so without this the claim is callable with the published anon key"
    )
    return found


@pytest.fixture(scope="module")
def function_grants(sql: str) -> list[str]:
    found = _statements(sql, rf"GRANT\s+[^;]*?{FUNCTION_TARGET}")
    assert found, (
        f"no GRANT on {FUNCTION}(integer) — after the REVOKE nothing could call it and the "
        "edge function's claim would fail closed on every run, i.e. the feed goes dark"
    )
    return found


# ── The file itself ──────────────────────────────────────────────────────────────


def test_migration_file_exists_and_is_the_only_064() -> None:
    """A second 064_* file would apply too, and this module would not know which it audited.

    db-migrate.yml keys ``olympus_schema_migrations`` on the full filename and only emits a
    ``::warning::`` for duplicate numeric prefixes, so nothing upstream stops the split.
    """
    numbered = sorted(MIGRATIONS_DIR.glob("064_*.sql"))
    assert numbered == [MIGRATION_PATH], f"expected exactly {MIGRATION_PATH.name}, found {numbered}"


def test_migration_is_not_self_wrapping(raw: str) -> None:
    """Deliberately the RAW source: db-migrate.yml's grep does not skip ``--`` comments.

    This file's header has to discuss the read-then-act race and transaction visibility to be
    any use to the next reader, and it must therefore backtick every mention of the token so
    the preceding character is not whitespace. Unbackticked, the deploy script applies the file
    without --single-transaction: a mid-file failure cannot roll back, and the DDL can commit
    with no row in ``olympus_schema_migrations`` — which makes the next deploy re-apply it.
    """
    hit = SELF_WRAP_REGEX.search(raw)
    assert hit is None, (
        f"a bare BEGIN; at offset {hit.start() if hit else -1} makes db-migrate.yml drop "
        "--single-transaction. A plpgsql `BEGIN` opening the function body is fine — it is "
        "followed by a statement, not a semicolon — so this is a real bare BEGIN;"
    )


# ── The lease row: exactly one, and claimable on the first ever call ─────────────


def test_create_table_is_idempotent(sql: str) -> None:
    assert re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(TABLE)}\b", sql, re.IGNORECASE
    ), "CREATE TABLE without IF NOT EXISTS aborts the whole transaction on a re-run"


def test_the_lease_is_a_single_row_enforced_by_a_check(table_body: str) -> None:
    """``CHECK (id = 1)`` is what makes "the lease" singular rather than conventional.

    The claim function is hard-coded to ``WHERE id = 1``. Without the constraint a second row
    can be inserted — by a later migration, a fixture, a careless operator — and it is
    invisible: the claim keeps working against row 1 while row 2 sits there implying the design
    supports multiple leases. Then someone builds on that reading.
    """
    assert re.search(r"CHECK\s*\(\s*id\s*=\s*1\s*\)", table_body, re.IGNORECASE), (
        f"{TABLE} has no `CHECK (id = 1)` single-row guard"
    )


def test_id_is_the_primary_key(table_body: str, columns: dict[str, str]) -> None:
    assert "id" in columns, f"{TABLE} has no `id` column: have {sorted(columns)}"
    definition = columns["id"].lower()
    assert definition.startswith("smallint"), f"id is `{columns['id']}`, expected smallint"
    inline_pk = "primary key" in definition
    table_pk = re.search(r"PRIMARY\s+KEY\s*\(\s*id\s*\)", table_body, re.IGNORECASE)
    assert inline_pk or table_pk, (
        "id is not the PRIMARY KEY; the seed INSERT's ON CONFLICT (id) needs a unique index to "
        "infer, so without it re-applying this migration raises 42P10 instead of doing nothing"
    )


def test_claimed_at_is_not_null_and_starts_infinitely_stale(columns: dict[str, str]) -> None:
    """Both halves are load-bearing, and both fail silently rather than loudly.

    NULL: ``claimed_at < cutoff`` is NULL, never true, so no caller ever wins the claim and the
    feed simply stops — a permanently fail-closed guard with no error anywhere. ``'-infinity'``:
    the seeded row must be older than any cutoff so the FIRST claim after deploy succeeds
    instead of waiting out one window against a NULL-ish or ``now()`` default.
    """
    assert "claimed_at" in columns, f"{TABLE} has no `claimed_at`: have {sorted(columns)}"
    definition = columns["claimed_at"].lower()
    assert definition.startswith(("timestamptz", "timestamp with time zone")), (
        f"claimed_at is `{columns['claimed_at']}`, expected timestamptz"
    )
    assert "not null" in definition, (
        "claimed_at is nullable — `claimed_at < cutoff` on NULL is NULL, so the UPDATE matches "
        "zero rows forever and no caller can ever claim the lease"
    )
    assert re.search(r"default\s+'-infinity'", definition, re.IGNORECASE), (
        "claimed_at has no `DEFAULT '-infinity'`; the seeded row would not be stale enough for "
        "the first claim to win, and a NOT NULL column with no default breaks the seed INSERT"
    )


def test_the_single_row_is_seeded_idempotently(sql: str) -> None:
    """``ON CONFLICT (id) DO NOTHING`` — the claim UPDATEs, so it cannot create the row.

    No row means the UPDATE matches nothing, ``FOUND`` is false, and every caller forever reads
    "someone else holds the window". The feed is dark and nothing logs an error. And this file
    is re-applied whenever its ledger row is missing, so a bare INSERT would raise 23505 and
    roll back the table with it.
    """
    seed = re.search(
        rf"INSERT\s+INTO\s+{re.escape(TABLE)}\s*\([^)]*\bid\b[^)]*\)\s*VALUES\s*\(\s*1\s*\)"
        r"(?P<tail>[^;]*);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert seed, f"no `INSERT INTO {TABLE} (id) VALUES (1)` seed — the lease row never exists"
    assert re.search(
        r"ON\s+CONFLICT\s*\(\s*id\s*\)\s*DO\s+NOTHING", seed.group("tail"), re.IGNORECASE
    ), "the seed INSERT is not `ON CONFLICT (id) DO NOTHING`; a re-run raises 23505"


# ── Access control: RLS with zero policies, and nothing granted to a client role ──


def test_row_level_security_is_enabled(sql: str) -> None:
    assert re.search(
        rf"ALTER\s+TABLE\s+{re.escape(TABLE)}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY\s*;",
        sql,
        re.IGNORECASE,
    ), f"{TABLE} never enables row level security"
    assert not re.search(r"DISABLE\s+ROW\s+LEVEL\s+SECURITY", sql, re.IGNORECASE), (
        "the migration disables RLS somewhere — the zero-policy denial becomes decorative"
    )


def test_the_lease_table_has_zero_policies(sql: str) -> None:
    """THE control, asserted as an absence — the same shape as 063's missing write policy.

    Under RLS an absent policy denies, so with no policy at all only ``rolbypassrls`` roles and
    the table owner reach this table. That is deliberate and complete: clients have no business
    reading the lease, and the claim function is SECURITY DEFINER so it runs as the owner.
    Adding "just a SELECT policy for anon" would hand every anon-key holder the exact timing
    oracle needed to race the cron for the window — while every other test here stays green.

    The ``ON <table>`` clause is part of the pattern so the phrase "CREATE POLICY" inside a
    ``RAISE ... HINT`` string cannot be mistaken for a statement.
    """
    policies = re.findall(
        rf"CREATE\s+POLICY\s+[\w\"]+\s+ON\s+{re.escape(TABLE)}\b", sql, re.IGNORECASE
    )
    assert not policies, (
        f"{len(policies)} policy/policies created on {TABLE}. Zero policies IS the control — "
        "do not complete the policy set."
    )


@pytest.mark.parametrize("role", REVOKED_ROLES)
def test_revoke_all_on_the_table_covers_public_and_both_client_roles(
    table_revokes: list[str], role: str
) -> None:
    matching = [
        statement
        for statement in table_revokes
        if re.search(rf"\b{role}\b", _roles_clause(statement), re.IGNORECASE)
    ]
    assert matching, (
        f"{role} is not named in any REVOKE on {TABLE}. Naming anon and authenticated but not "
        "PUBLIC leaves the privileges they both inherit through PUBLIC in place."
    )
    assert any(re.search(r"REVOKE\s+ALL\b", statement, re.IGNORECASE) for statement in matching), (
        f"the REVOKE covering {role} on {TABLE} is not `REVOKE ALL`; an enumerated list is a "
        "list someone has to keep in sync with Postgres, and nothing here needs any privilege"
    )


@pytest.mark.parametrize("role", REVOKED_ROLES)
def test_no_client_role_may_execute_the_claim(function_revokes: list[str], role: str) -> None:
    """The security assertion of this module, and it runs in BOTH directions.

    Quota: without the revoke an attacker skips the edge function entirely and drives Finnhub
    spend by... no — worse. Starvation: they call the claim directly in a tight loop, win every
    window, and the legitimate cron finds the lease always fresh and never fetches. The feed
    freezes with no error, no 429, and no unusual traffic on the function itself. That is a
    denial of *freshness*, and this REVOKE is the whole of its defense — the claim is SECURITY
    DEFINER, so nothing inside it re-checks the caller.
    """
    matching = [
        statement
        for statement in function_revokes
        if re.search(rf"\b{role}\b", _roles_clause(statement), re.IGNORECASE)
    ]
    assert matching, (
        f"{role} is not named in any REVOKE on {FUNCTION}(integer). Postgres grants EXECUTE to "
        "PUBLIC on every new function, so an unnamed role keeps it and can starve the cron by "
        "claiming every window itself."
    )
    assert any(re.search(r"REVOKE\s+ALL\b", statement, re.IGNORECASE) for statement in matching), (
        f"the REVOKE covering {role} on {FUNCTION} is not `REVOKE ALL`"
    )


def test_only_service_role_is_granted_execute(function_grants: list[str]) -> None:
    """``service_role`` is the edge function's credential and the only intended caller."""
    for statement in function_grants:
        granted = _roles(statement, "TO")
        assert granted == {"service_role"}, (
            f"EXECUTE on {FUNCTION} is granted to {sorted(granted)}; service_role is the only "
            "credential that may claim a refresh window"
        )
    assert any(
        re.search(r"GRANT\s+EXECUTE\b", statement, re.IGNORECASE) for statement in function_grants
    ), f"no `GRANT EXECUTE` on {FUNCTION} — the edge function cannot call its own guard"


def test_nothing_on_the_lease_table_is_granted_to_a_client_role(sql: str) -> None:
    """A GRANT here would survive the REVOKE above it and quietly undo the zero-policy design.

    SELECT alone leaks the timing oracle; UPDATE hands over the lease outright. Neither is
    needed by anything: the claim runs SECURITY DEFINER as the table's owner.
    """
    for statement in _statements(sql, rf"GRANT\s+[^;]*?{TABLE_TARGET}"):
        granted = _roles(statement, "TO")
        assert not granted & set(CLIENT_ROLES), (
            f"{sorted(granted & set(CLIENT_ROLES))} granted privileges on {TABLE}: "
            f"{statement.strip()}"
        )


# ── The claim itself: one conditional UPDATE, and nothing read before it ─────────


def test_the_function_is_security_definer_with_an_empty_search_path(create_function: str) -> None:
    """SECURITY DEFINER without a pinned search_path is the classic privilege-escalation bug.

    The function runs as its owner (the migration applier, i.e. a superuser-adjacent role) and
    bypasses both RLS and the table REVOKEs — which is exactly why it can claim a table nobody
    else may touch. With a caller-controlled ``search_path``, an unprivileged role that can
    create a schema can shadow any unqualified name the body resolves and have it executed with
    the owner's rights. ``SET search_path = ''`` forces every reference to be schema-qualified;
    the body's ``public.prices_live_lease`` and pg_catalog builtins already are.
    """
    assert re.search(r"SECURITY\s+DEFINER", create_function, re.IGNORECASE), (
        f"{FUNCTION} is not SECURITY DEFINER, so service_role's own privileges apply — and the "
        f"lease table has REVOKE ALL plus RLS with zero policies, so the claim would fail 42501"
    )
    assert re.search(r"SET\s+search_path\s*(?:=|TO)\s*''", create_function, re.IGNORECASE), (
        "the SECURITY DEFINER function has no `SET search_path = ''`; an unqualified name in "
        "the body could be shadowed by a schema the caller controls and run as the owner"
    )
    assert re.search(r"LANGUAGE\s+plpgsql", create_function, re.IGNORECASE), (
        f"{FUNCTION} is not LANGUAGE plpgsql — `FOUND` and `RAISE` are plpgsql-only"
    )
    assert re.search(r"RETURNS\s+boolean", create_function, re.IGNORECASE), (
        "the claim must RETURN boolean; the edge function fails closed on anything that is not "
        "exactly `true`, so a void or record return silently disables the feed"
    )


def test_a_useless_window_raises_instead_of_disabling_the_guard(function_body: str) -> None:
    """``min_age_seconds`` of 0 or NULL would turn the guard off, so it must raise.

    0: ``claimed_at < clock_timestamp()`` is true for the row this statement is about to write,
    so every caller wins and the rate guard is gone — with the RPC still returning ``true`` and
    every log line looking healthy. NULL: the whole predicate is NULL, nobody ever wins, and
    the feed goes dark just as quietly. Both are misconfigurations that must be loud.
    """
    guard = re.search(
        rf"IF\s+[^;]*{ARG}[^;]*?THEN(?P<branch>.*?)END\s+IF\s*;",
        function_body,
        re.IGNORECASE | re.DOTALL,
    )
    assert guard, f"no `IF ... {ARG} ... THEN ... END IF;` validation branch in {FUNCTION}"
    condition = function_body[: guard.start("branch")]
    assert re.search(rf"{ARG}\s+IS\s+NULL", condition, re.IGNORECASE), (
        f"{ARG} is never checked for NULL; a NULL window makes the predicate NULL and no caller "
        "can ever claim"
    )
    assert re.search(rf"{ARG}\s*<\s*1\b", condition, re.IGNORECASE), (
        f"{ARG} is not rejected below 1; a 0 disables the rate guard silently"
    )
    assert re.search(r"RAISE\s+EXCEPTION", guard.group("branch"), re.IGNORECASE), (
        "the validation branch does not RAISE — a guard that logs and continues is not a guard"
    )


def test_the_claim_is_one_conditional_update(function_body: str) -> None:
    """One statement, so "check the lease" and "take the lease" cannot be pulled apart.

    Concurrent callers serialize on the lease row's lock inside this single UPDATE, then
    re-evaluate the WHERE clause against the committed new ``claimed_at`` under READ COMMITTED
    and match zero rows. Split it into a SELECT and an UPDATE and the six-second race described
    in the module docstring comes straight back.
    """
    countable = _strip_sql_literals(function_body)
    updates = re.findall(r"\bUPDATE\b", countable, re.IGNORECASE)
    assert len(updates) == 1, (
        f"expected exactly one UPDATE in {FUNCTION}, found {len(updates)} — a second write "
        "means the decision and the claim are separate steps again"
    )

    statement = re.search(
        rf"UPDATE\s+{re.escape(TABLE)}\s+SET\s+(?P<set>.*?)\s+WHERE\s+(?P<where>.*?);",
        function_body,
        re.IGNORECASE | re.DOTALL,
    )
    assert statement, f"no `UPDATE {TABLE} SET ... WHERE ...;` in {FUNCTION}"
    assert re.search(
        r"claimed_at\s*=\s*clock_timestamp\(\)", statement.group("set"), re.IGNORECASE
    ), (
        "the UPDATE does not set `claimed_at = clock_timestamp()`; without stamping the row the "
        "WHERE clause stays true and every concurrent caller wins"
    )

    where = statement.group("where")
    assert re.search(r"\bid\s*=\s*1\b", where, re.IGNORECASE), (
        "the UPDATE is not scoped to `id = 1`, so it would claim every row the table ever holds"
    )
    assert re.search(r"claimed_at\s*<", where, re.IGNORECASE), (
        "the WHERE clause has no `claimed_at <` age predicate — an unconditional UPDATE always "
        "matches, always returns FOUND, and rate-limits nothing"
    )
    assert re.search(rf"\b{ARG}\b", where, re.IGNORECASE), (
        f"the age predicate ignores {ARG}, so the window is hard-coded and the edge function's "
        "MIN_REFRESH_SECONDS is decorative"
    )
    assert re.search(r"make_interval\s*\(\s*secs\s*=>", where, re.IGNORECASE), (
        f"the cutoff is not `make_interval(secs => {ARG})`; multiplying an interval literal by "
        "an integer works but `'1 second' * n` is the form that silently misreads a NULL"
    )


def test_the_claim_never_reads_before_it_writes(function_body: str) -> None:
    """No SELECT from the lease, no advisory lock — the two shapes that look equivalent.

    A ``SELECT ... FROM public.prices_live_lease`` followed by a decision is read-then-act, and
    the window between the two steps is the whole vulnerability. A session advisory lock is not
    a substitute in this deployment: PostgREST hands out a fresh session per RPC call, so the
    lock is released when the RPC returns — roughly six seconds before the fetch it is supposed
    to be covering has finished.

    Asserted on literal-stripped SQL so the RAISE messages this file is expected to carry can
    keep naming both rejected designs.
    """
    countable = _strip_sql_literals(function_body)
    assert not re.search(
        rf"SELECT\b[^;]*\bFROM\s+{re.escape(TABLE)}", countable, re.IGNORECASE | re.DOTALL
    ), (
        f"{FUNCTION} SELECTs from {TABLE} before deciding. The UPDATE's own WHERE clause is the "
        "read, and it is the only one that cannot be raced."
    )
    assert not re.search(r"pg_(?:try_)?advisory", countable, re.IGNORECASE), (
        "an advisory lock is not a substitute for the conditional UPDATE — PostgREST's "
        "session-per-call means it releases before the fetch it would need to protect"
    )


def test_the_claim_returns_found(function_body: str) -> None:
    """``FOUND`` is how one statement reports a winner; it is not decoration.

    After the UPDATE, ``FOUND`` is true for the single caller whose WHERE clause matched and
    false for everyone who blocked on the row and then found it too fresh. Return a constant
    ``true`` instead and every caller believes it won — the guard is gone and nothing in the
    edge function can tell.
    """
    assert re.search(r"RETURN\s+FOUND\s*;", function_body, re.IGNORECASE), (
        f"{FUNCTION} does not `RETURN FOUND;` — that boolean is the entire output of the claim"
    )
    assert not re.search(r"RETURN\s+(?:true|false)\s*;", function_body, re.IGNORECASE), (
        "the claim returns a literal boolean somewhere; only FOUND reflects whether this "
        "caller's conditional UPDATE actually matched the lease row"
    )


def _roles_clause(statement: str) -> str:
    """The ``FROM ...`` / ``TO ...`` tail of a REVOKE/GRANT, so role names never match the target.

    Without this, ``REVOKE ALL ON public.prices_live_lease FROM anon`` would report ``public``
    as a revoked role on the strength of the schema qualifier in its own target.
    """
    match = re.search(r"\b(?:FROM|TO)\b(?P<roles>[^;]*)", statement, re.IGNORECASE)
    return match.group("roles") if match else ""
