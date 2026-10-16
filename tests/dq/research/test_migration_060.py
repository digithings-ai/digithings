"""Unit tests for migration 060 (public write-grant lockdown, #1757).

Hermetic pure-SQL parse checks in the ``test_migration_051.py`` mold: no Postgres,
no network. Three guarantees are load-bearing and each has a production failure mode
if it regresses:

1. The revoke must be **schema-wide**, covering every relation in ``public`` — the
   platform default granted the public roles full DML on all 35 base tables plus the
   two under-granted views (``atlas_run_health``, ``price_history_tickers``).
2. It must list the write privileges **explicitly** and never touch ``SELECT``. A
   ``REVOKE ALL`` in the ``ALTER DEFAULT PRIVILEGES`` statement would silently strip
   reads from the next curated view, and ``safeSelect`` turns a PostgREST 42501 into
   an empty panel rather than an error.
3. It must not name ``supabase_admin`` in a ``FOR ROLE`` clause. ``postgres`` is not a
   member of that role, so the statement would raise — and ``db-migrate.yml`` pipes
   each file through ``psql --single-transaction``, rolling back the whole migration.

Plus a documentation check: ``supabase/SCHEMA.md`` claimed migration 041 shipped a
``REVOKE ALL``. It never did, and that false claim is why the gap survived review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "060_lock_public_write_grants.sql"
)
SCHEMA_DOC_PATH = REPO_ROOT / "digiquant" / "supabase" / "SCHEMA.md"

# Exactly the non-SELECT table privileges the public roles hold by platform default.
# MAINTAIN is deliberately absent (PG17-only, zero matviews in `public`) and SELECT must
# never appear.
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

# The two views migrations 041 and 018 granted without a preceding REVOKE.
UNDER_GRANTED_VIEWS = ("atlas_run_health", "price_history_tickers")


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def statements(sql: str) -> str:
    """The migration with comment lines stripped, so assertions bind to executable SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def table_revoke(statements: str) -> str:
    match = re.search(r"REVOKE\s+(?P<body>[^;]*?ON ALL TABLES IN SCHEMA public[^;]*);", statements)
    assert match, "missing schema-wide REVOKE ... ON ALL TABLES IN SCHEMA public"
    return match.group(0)


@pytest.fixture(scope="module")
def default_privileges(statements: str) -> str:
    match = re.search(r"ALTER DEFAULT PRIVILEGES[^;]*;", statements)
    assert match, "missing ALTER DEFAULT PRIVILEGES statement"
    return match.group(0)


@pytest.mark.unit
class TestSchemaWideRevoke:
    def test_revoke_is_schema_wide_not_per_table(self, table_revoke: str) -> None:
        # A two-view fix would leave the other 35 relations one DISABLE ROW LEVEL
        # SECURITY away from being world-writable, which is #1757's actual claim.
        assert "ON ALL TABLES IN SCHEMA public" in table_revoke

    @pytest.mark.parametrize("privilege", WRITE_PRIVILEGES)
    def test_revokes_every_write_privilege(self, table_revoke: str, privilege: str) -> None:
        assert re.search(rf"\b{privilege}\b", table_revoke), f"{privilege} not revoked"

    @pytest.mark.parametrize("role", ("anon", "authenticated"))
    def test_covers_both_public_roles(self, table_revoke: str, role: str) -> None:
        assert re.search(rf"FROM[^;]*\b{role}\b", table_revoke)

    def test_service_role_is_never_narrowed(self, statements: str) -> None:
        # service_role is the only writer: all five production workflows, every Python
        # connector, and the prices-live edge function authenticate with it.
        assert "service_role" not in statements


@pytest.mark.unit
class TestUnderGrantedViewsAreNamedExplicitly:
    """The one live exploit is through a view, so it must not rest on `ALL TABLES` semantics."""

    @pytest.fixture(scope="class")
    def view_revoke(self, statements: str) -> str:
        for revoke in re.findall(r"REVOKE[^;]*;", statements):
            if "ALL TABLES" not in revoke:
                return revoke
        pytest.fail("no per-relation REVOKE — coverage of the two views rests on ALL TABLES")

    @pytest.mark.parametrize("view", UNDER_GRANTED_VIEWS)
    def test_names_the_view(self, view_revoke: str, view: str) -> None:
        assert f"public.{view}" in view_revoke

    @pytest.mark.parametrize("privilege", WRITE_PRIVILEGES)
    def test_revokes_every_write_privilege(self, view_revoke: str, privilege: str) -> None:
        assert re.search(rf"\b{privilege}\b", view_revoke), f"{privilege} not revoked on the views"


@pytest.mark.unit
class TestSelectIsPreserved:
    def test_no_blanket_revoke_all(self, statements: str) -> None:
        assert not re.search(r"REVOKE\s+ALL\b", statements, re.I), (
            "REVOKE ALL would strip SELECT and blank the dashboard"
        )

    def test_select_is_never_revoked(self, statements: str) -> None:
        for revoke in re.findall(r"REVOKE[^;]*;", statements, re.I):
            assert not re.search(r"\bSELECT\b", revoke, re.I), f"SELECT revoked in: {revoke}"

    @pytest.mark.parametrize("view", UNDER_GRANTED_VIEWS)
    def test_reasserts_read_grant_on_under_granted_views(self, statements: str, view: str) -> None:
        assert re.search(
            rf"GRANT SELECT ON public\.{view}\s+TO anon, authenticated",
            statements,
        ), f"missing explicit read grant for {view}"

    def test_grants_nothing_but_select(self, statements: str) -> None:
        for grant in re.findall(r"GRANT[^;]*;", statements, re.I):
            assert re.match(r"GRANT SELECT\b", grant.strip(), re.I), f"non-SELECT grant: {grant}"


@pytest.mark.unit
class TestDefaultPrivileges:
    def test_narrows_future_relations(self, default_privileges: str) -> None:
        assert "IN SCHEMA public" in default_privileges
        assert re.search(r"\bREVOKE\b[^;]*\bON TABLES\b", default_privileges)

    @pytest.mark.parametrize("privilege", WRITE_PRIVILEGES)
    def test_lists_write_privileges_explicitly(
        self, default_privileges: str, privilege: str
    ) -> None:
        assert re.search(rf"\b{privilege}\b", default_privileges)

    def test_uses_the_implicit_postgres_grantor(self, default_privileges: str) -> None:
        # `FOR ROLE supabase_admin` raises "must be a member of role" and, under
        # psql --single-transaction, rolls the entire migration back.
        assert "FOR ROLE" not in default_privileges.upper()
        assert "supabase_admin" not in default_privileges


@pytest.mark.unit
class TestMigrationIsNonDestructive:
    def test_touches_no_data_and_no_objects(self, statements: str) -> None:
        assert not re.search(
            r"\bDROP\b|\bTRUNCATE TABLE\b|\bDELETE FROM\b|\bALTER TABLE\b|\bCREATE\b",
            statements,
            re.I,
        )

    def test_does_not_change_rls_policies(self, statements: str) -> None:
        assert "POLICY" not in statements.upper()
        assert "ROW LEVEL SECURITY" not in statements.upper()

    def test_is_not_self_wrapping(self, statements: str) -> None:
        # db-migrate.yml greps for a bare BEGIN; and switches transaction handling. This
        # file must take the --single-transaction path so a partial failure rolls back.
        assert not re.search(r"(^|\s)BEGIN\s*;", statements, re.I)


@pytest.mark.unit
class TestSchemaDocClaimIsCorrected:
    """SCHEMA.md asserted a narrowing migration 041 never implemented (#1757)."""

    @pytest.fixture(scope="class")
    def views_bullet(self) -> str:
        doc = SCHEMA_DOC_PATH.read_text(encoding="utf-8")
        match = re.search(r"^- \*\*Views \(migrations[^\n]*(?:\n(?!- \*\*|#)[^\n]*)*", doc, re.M)
        assert match, "SCHEMA.md lost its RLS-section bullet about the curated views"
        return " ".join(match.group(0).split())

    def test_no_sentence_credits_041_with_a_revoke(self, views_bullet: str) -> None:
        # The pre-060 text read "Views (migrations 041, 050): … with explicit `REVOKE ALL`
        # + `GRANT SELECT TO anon, authenticated`" — one sentence naming 041 and claiming a
        # narrowing only 050/052 ever performed. That false claim is why the gap survived.
        for sentence in views_bullet.split(". "):
            assert not ("041" in sentence and re.search(r"REVOKE ALL", sentence)), (
                f"SCHEMA.md still credits 041 with a REVOKE it never shipped: {sentence}"
            )

    def test_cites_the_lockdown_migration(self) -> None:
        doc = SCHEMA_DOC_PATH.read_text(encoding="utf-8")
        assert "060" in doc, "SCHEMA.md must record the 060 write-grant lockdown"
