"""Unit tests for migration 062 — Realtime broadcast authorization (#1807).

Hermetic source/SQL audit in the ``test_migration_051.py`` / ``test_migration_061.py``
mold: no Postgres, no network, no Deno.

Realtime Authorization is **one mechanism spread over three files**, and every failure
mode here is a two-file disagreement, so the tests deliberately span all three:

* ``digiquant/supabase/migrations/062_realtime_broadcast_authorization.sql``
* ``digiquant/supabase/functions/prices-live/index.ts``          (publisher)
* ``frontend/digiquant-web/lib/live/useLivePrices.ts``           (subscriber)

The guarantees, in order of how expensive they are to get wrong:

1. **No anon INSERT policy on ``realtime.messages``.** This absence *is* the fix. Supabase
   grants ``anon`` INSERT on that table, so an insert policy reachable by ``anon`` would
   re-open forged broadcasts — the whole vulnerability — while every other test still
   passed.
2. **Both clients join privately.** Realtime consults RLS *only* for private channels, so
   a public subscriber makes the policies inert (hole stays open) and a public publisher
   risks a dark feed against a private subscriber.
3. **The anon SELECT policy is topic-scoped.** ``USING (true)`` would authorize anon to
   receive on *every* Realtime topic in the project, not just ``prices:live``.
4. **The ownership preflight raises rather than swallows.** A migration that skips the DDL
   quietly, combined with a shipped ``private: true``, is the silent-outage scenario.
5. **The file is not self-wrapping and stays idempotent**, so ``db-migrate.yml`` applies it
   atomically and a re-run is safe.

``pytestmark = pytest.mark.unit`` is mandatory, not decorative: ``test-digiquant.yml``
runs ``pytest tests/dq/ -m unit``, and the existing migration tests in this directory
carry no marker — ``pytest tests/dq/atlas/test_migration_061.py -m unit --co`` collects
``23 items / 23 deselected / 0 selected``. Without the marker this file would never run in
CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "062_realtime_broadcast_authorization.sql"
)
PUBLISHER_PATH = REPO_ROOT / "digiquant" / "supabase" / "functions" / "prices-live" / "index.ts"
SUBSCRIBER_PATH = REPO_ROOT / "frontend" / "digiquant-web" / "lib" / "live" / "useLivePrices.ts"
README_PATH = REPO_ROOT / "digiquant" / "supabase" / "README.md"

TOPIC = "prices:live"

# Verbatim from .github/workflows/db-migrate.yml: a match makes the deploy script run the
# file WITHOUT --single-transaction.
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

# Roles that must never hold an INSERT (broadcast) policy on this topic.
FORBIDDEN_WRITERS = ("anon", "authenticated", "public")


def _strip_sql_comments(sql: str) -> str:
    """Drop whole-line ``--`` comments so assertions bind to executable SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _strip_ts_comments(src: str) -> str:
    """Drop comment-only lines so a comment mentioning the fix cannot satisfy a test.

    Line-based on purpose: it removes ``//`` lines and ``/** … */`` block bodies without
    mangling ``https://`` inside string literals (which a naive ``//`` split would).
    """
    kept: list[str] = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("//", "/*", "*/", "*")):
            continue
        kept.append(line)
    return "\n".join(kept)


@pytest.fixture(scope="module")
def sql() -> str:
    return _strip_sql_comments(MIGRATION_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def publisher() -> str:
    return _strip_ts_comments(PUBLISHER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def subscriber() -> str:
    return _strip_ts_comments(SUBSCRIBER_PATH.read_text(encoding="utf-8"))


def _policies(sql: str) -> list[dict[str, str]]:
    """Parse each ``CREATE POLICY`` statement into ``{name, table, cmd, roles, body}``.

    The ``ON <table>`` clause is part of the pattern so the phrase "CREATE POLICY" inside
    a ``RAISE ... HINT`` string is not mistaken for a statement.
    """
    out: list[dict[str, str]] = []
    for match in re.finditer(
        r"CREATE\s+POLICY\s+(?P<name>[\w\"]+)\s+ON\s+(?P<table>[\w\".]+)(?P<body>.*?);",
        sql,
        re.IGNORECASE | re.DOTALL,
    ):
        body = match.group("body")
        cmd = re.search(r"\bFOR\s+(SELECT|INSERT|UPDATE|DELETE|ALL)\b", body, re.IGNORECASE)
        roles = re.search(r"\bTO\s+([\w\s,\"]+?)(?=\bUSING\b|\bWITH\b|$)", body, re.IGNORECASE)
        out.append(
            {
                "name": match.group("name").strip('"'),
                "table": match.group("table").replace('"', "").lower(),
                "cmd": (cmd.group(1).upper() if cmd else ""),
                "roles": (roles.group(1) if roles else "").replace('"', "").lower(),
                "body": body,
            }
        )
    return out


# ── The file itself ──────────────────────────────────────────────────────────────


def test_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file(), f"missing {MIGRATION_PATH}"


def test_migration_is_not_self_wrapping(sql: str) -> None:
    """A stray ``BEGIN;`` would make db-migrate.yml drop --single-transaction."""
    assert not SELF_WRAP_REGEX.search(sql), (
        "migration contains a bare BEGIN; — db-migrate.yml would then apply it WITHOUT "
        "--single-transaction, so a mid-file failure could not roll back"
    )


def test_every_policy_is_dropped_before_it_is_created(sql: str) -> None:
    """Idempotence: re-applying the migration must not fail on a duplicate policy."""
    created = _policies(sql)
    assert created, "no CREATE POLICY statements found"
    for policy in created:
        assert re.search(
            rf"DROP\s+POLICY\s+IF\s+EXISTS\s+{re.escape(policy['name'])}\b",
            sql,
            re.IGNORECASE,
        ), f"{policy['name']} is created without a preceding DROP POLICY IF EXISTS"


def test_policies_target_realtime_messages(sql: str) -> None:
    created = _policies(sql)
    assert created, "no CREATE POLICY statements found"
    for policy in created:
        assert policy["table"] == "realtime.messages", (
            f"policy {policy['name']} targets {policy['table']}, not realtime.messages — "
            "that is the only table Realtime consults for private-channel authorization"
        )


# ── Guarantee 1: anon must not be able to broadcast ──────────────────────────────


def test_no_insert_policy_is_reachable_by_anon(sql: str) -> None:
    """THE fix: absent INSERT policy = anon cannot broadcast forged quotes."""
    for policy in _policies(sql):
        if policy["cmd"] not in {"INSERT", "ALL"}:
            continue
        roles = {role.strip() for role in policy["roles"].split(",") if role.strip()}
        offenders = roles.intersection(FORBIDDEN_WRITERS)
        assert not offenders, (
            f"policy {policy['name']} grants {policy['cmd']} to {sorted(offenders)} on "
            "realtime.messages — that re-opens forged broadcasts from the public anon key"
        )
        # An INSERT policy with no TO clause defaults to PUBLIC, i.e. anon included.
        assert roles, (
            f"policy {policy['name']} is an INSERT policy with no TO clause, so it applies "
            "to PUBLIC (including anon) — scope it to service_role"
        )


def test_only_service_role_may_broadcast(sql: str) -> None:
    writers = [p for p in _policies(sql) if p["cmd"] == "INSERT"]
    assert writers, "no INSERT policy — the service-role publisher's authority is unstated"
    for policy in writers:
        assert "service_role" in policy["roles"], (
            f"INSERT policy {policy['name']} is not scoped TO service_role"
        )


# ── Guarantee 3: the receive policy is scoped to this topic and to broadcast ─────


def test_receive_policy_is_scoped_to_the_topic_and_to_broadcast(sql: str) -> None:
    readers = [p for p in _policies(sql) if p["cmd"] == "SELECT"]
    assert readers, (
        "no SELECT policy on realtime.messages — with `private: true` on the client every "
        "subscriber would be refused the join and the live feed would go dark"
    )
    for policy in readers:
        assert "anon" in policy["roles"], (
            f"SELECT policy {policy['name']} does not include anon; digiquant.io "
            "subscribes with the anon key"
        )
        assert f"'{TOPIC}'" in policy["body"], (
            f"SELECT policy {policy['name']} is not scoped to realtime.topic() = "
            f"'{TOPIC}' — an unscoped policy authorizes anon on EVERY Realtime topic"
        )
        assert "realtime.topic()" in policy["body"], (
            f"SELECT policy {policy['name']} must scope on realtime.topic()"
        )
        assert re.search(r"extension\s*=\s*'broadcast'", policy["body"], re.IGNORECASE), (
            f"SELECT policy {policy['name']} does not restrict extension = 'broadcast', so "
            "it also authorizes presence/postgres_changes traffic"
        )


# ── Guarantee 4: the ownership preflight fails loudly ────────────────────────────


def test_migration_preflights_ownership_and_raises(sql: str) -> None:
    """`postgres` does not own realtime.messages; the failure must be legible, not swallowed."""
    assert "pg_has_role" in sql, (
        "no ownership preflight — CREATE POLICY on realtime.messages requires table "
        "ownership, and as `postgres` this migration raises a bare 42501"
    )
    assert re.search(r"RAISE\s+EXCEPTION", sql, re.IGNORECASE), (
        "the preflight must RAISE EXCEPTION; a notice-and-continue would record 062 as "
        "applied while creating no policy — the silent-outage case"
    )
    assert not re.search(
        r"EXCEPTION\s+WHEN\s+(insufficient_privilege|others)", sql, re.IGNORECASE
    ), (
        "the migration swallows the privilege error — 062 would be recorded as applied "
        "with no policies present, and a shipped `private: true` client would then take "
        "the live price feed dark"
    )


# ── Guarantee 2: both ends of the channel are private ───────────────────────────


def _asserts_private_channel(src: str, topic_const: str) -> bool:
    """True when the channel is opened with `config: { private: true }`."""
    match = re.search(
        rf"\.channel\(\s*{re.escape(topic_const)}\s*,(?P<opts>.*?)\)\s*(?:;|\.|$)",
        src,
        re.DOTALL,
    )
    if match is None:
        return False
    opts = re.sub(r"\s+", "", match.group("opts"))
    return "config:{private:true}" in opts


def test_subscriber_joins_a_private_channel(subscriber: str) -> None:
    assert 'const BROADCAST_CHANNEL = "prices:live"' in subscriber, (
        "BROADCAST_CHANNEL is no longer bound to 'prices:live' — retarget this test"
    )
    assert _asserts_private_channel(subscriber, "BROADCAST_CHANNEL"), (
        "useLivePrices subscribes to prices:live WITHOUT config: { private: true }. "
        "Realtime consults the realtime.messages policies only for private channels, so a "
        "public join leaves the channel forgeable by anyone holding the bundled anon key"
    )


def test_publisher_broadcasts_on_a_private_channel(publisher: str) -> None:
    assert 'const CHANNEL = "prices:live"' in publisher, (
        "CHANNEL is no longer bound to 'prices:live' — retarget this test"
    )
    assert _asserts_private_channel(publisher, "CHANNEL"), (
        "prices-live broadcasts WITHOUT config: { private: true }; channel.send() puts "
        "`private: this.private` in the /realtime/v1/api/broadcast body, so publisher and "
        "subscriber must agree on the flag or delivery may stop"
    )


# ── Docs: the runbook is the outage prevention ──────────────────────────────────


def test_readme_documents_the_private_subscribe(publisher: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    snippet = re.search(r"\.channel\(\"prices:live\"(?P<rest>[^)]*)\)", readme)
    assert snippet is not None, "README no longer shows the prices:live subscribe snippet"
    assert "private: true" in snippet.group("rest"), (
        "the README subscribe snippet still joins prices:live publicly — copying it "
        "re-introduces the forged-broadcast hole"
    )


def test_readme_orders_policies_before_the_client() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert "Rolling out Realtime authorization" in readme, (
        "no ordered rollout runbook; applying the client half first takes the live feed dark"
    )
    migration_step = readme.find("Apply migration `062`")
    frontend_step = readme.find("Let the frontend reach production last")
    assert migration_step != -1 and frontend_step != -1, "rollout steps missing from README"
    assert migration_step < frontend_step, (
        "the runbook must order the migration BEFORE the frontend deploy"
    )
