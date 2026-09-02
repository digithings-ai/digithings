"""Structural contract tests for T0 tenancy migrations 096–098.

# score:allow todo

Mirrors the atlas ``test_migration_0XX.py`` style: parse SQL on disk, never talk to
live Supabase. Executable two-JWT RLS proof lands with T1; here we assert policies
exist, anon policies are untouched, seeds are idempotent, and every widened UNIQUE
is enumerated.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from digiquant.dashboard.tenancy import (
    house_workspace_id,
    house_workspace_row,
    system_workspace_id,
    system_workspace_row,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M096 = MIGRATIONS_DIR / "096_workspaces_tenancy_tables.sql"
M097 = MIGRATIONS_DIR / "097_workspaces_tenant_columns.sql"
M098 = MIGRATIONS_DIR / "098_workspaces_rls_policies.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

# Constraint ADDs this WP makes (097 header + body must agree).
# Legacy keys are KEPT alongside; P6 drops them after writers are patched.
ADDED_WIDENED_UNIQUES = (
    ("uq_positions_workspace_date_ticker", "workspace_id, date, ticker"),
    ("uq_position_events_workspace_date_ticker", "workspace_id, date, ticker"),
    ("uq_nav_history_workspace_date", "workspace_id, date"),
    ("uq_portfolio_metrics_workspace_date", "workspace_id, date"),
)

LEGACY_KEYS_KEPT = (
    "positions_date_ticker_key",
    "position_events_date_ticker_key",
    "nav_history_pkey",
    "portfolio_metrics_date_key",
)

PRIVATE_BOOK_TABLES = (
    "positions",
    "position_events",
    "nav_history",
    "portfolio_metrics",
    "portfolio_ledger_commits",
    "portfolio_ledger_decision_intents",
    "portfolio_ledger_requested_targets",
    "portfolio_ledger_target_adjustments",
    "portfolio_ledger_approved_targets",
    "portfolio_ledger_order_intents",
    "portfolio_ledger_paper_executions",
    "portfolio_ledger_holding_lots",
    "olympus_accounting_periods",
    "olympus_accounting_contributions",
    "olympus_accounting_holdings",
)

PRIVATE_SET_TABLES = (
    *PRIVATE_BOOK_TABLES,
    "olympus_profile_config",
)

# Existing anon_read surfaces — 098 must not DROP / recreate these.
ANON_READ_TABLES = (
    "daily_snapshots",
    "positions",
    "theses",
    "position_events",
    "documents",
    "nav_history",
    "benchmark_history",
    "portfolio_metrics",
)

# K3/K4/K5 tables — must be skipped with an explicit comment, not silently omitted.
SKIPPED_K_TRACK = (
    "broker_connections",
    "broker_orders",
    "broker_executions",
    "broker_position_snapshots",
    "notification_prefs",
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw_096() -> str:
    assert M096.is_file(), f"migration missing: {M096}"
    return M096.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def raw_097() -> str:
    assert M097.is_file(), f"migration missing: {M097}"
    return M097.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def raw_098() -> str:
    assert M098.is_file(), f"migration missing: {M098}"
    return M098.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_096(raw_096: str) -> str:
    return _strip_comments(raw_096)


@pytest.fixture(scope="module")
def sql_097(raw_097: str) -> str:
    return _strip_comments(raw_097)


@pytest.fixture(scope="module")
def sql_098(raw_098: str) -> str:
    return _strip_comments(raw_098)


def test_migration_numbers_are_096_097_098_only(sql_096: str, sql_097: str, sql_098: str) -> None:
    """T0 allocates 096–098; must not CREATE a 099_* migration (K3 owns 099)."""
    assert sorted(MIGRATIONS_DIR.glob("096_*.sql")) == [M096]
    assert sorted(MIGRATIONS_DIR.glob("097_*.sql")) == [M097]
    assert sorted(MIGRATIONS_DIR.glob("098_*.sql")) == [M098]
    # Sibling K3 may land 099 on its own branch; assert T0 SQL never creates it.
    for sql in (sql_096, sql_097, sql_098):
        assert not re.search(r"\b099_", sql), "T0 must not reference migration 099"
        assert not re.search(
            r"CREATE\s+TABLE\s+[^;]*broker_connections",
            sql,
            re.IGNORECASE,
        )
    numbers = sorted(
        int(p.name.split("_", 1)[0]) for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")
    )
    assert numbers.index(96) == numbers.index(95) + 1
    assert numbers.index(97) == numbers.index(96) + 1
    assert numbers.index(98) == numbers.index(97) + 1


@pytest.mark.parametrize("raw_fixture", ["raw_096", "raw_097", "raw_098"])
def test_migrations_remain_single_transaction_compatible(
    raw_fixture: str, request: pytest.FixtureRequest
) -> None:
    raw = request.getfixturevalue(raw_fixture)
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


# ---------------------------------------------------------------------------
# 096 — tables + seeds
# ---------------------------------------------------------------------------


def test_096_creates_required_tables(sql_096: str) -> None:
    for table in (
        "workspaces",
        "workspace_members",
        "stripe_events",
        "job_runs",
        "audit_log",
    ):
        assert re.search(
            rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.{table}\b",
            sql_096,
            re.IGNORECASE,
        ), table


def test_096_plan_tier_check_matches_spec_d1(sql_096: str) -> None:
    assert re.search(
        r"plan_tier\s+text\s+NOT NULL\s+DEFAULT\s+'free'\s*"
        r"CHECK\s*\(\s*plan_tier\s+IN\s*\(\s*'free'\s*,\s*'baseline'\s*,\s*'custom'\s*,\s*'enterprise'\s*\)\s*\)",
        sql_096,
        re.IGNORECASE | re.DOTALL,
    )
    assert "'pro'" not in sql_096


def test_096_exactly_one_system_workspace_partial_unique(sql_096: str) -> None:
    assert re.search(
        r"CREATE\s+UNIQUE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+uq_workspaces_one_system_row\b",
        sql_096,
        re.IGNORECASE,
    )
    assert re.search(
        r"ON\s+public\.workspaces\s*\(\s*type\s*\)\s*WHERE\s+type\s*=\s*'system'",
        sql_096,
        re.IGNORECASE,
    )


def test_096_seed_inserts_are_structurally_idempotent(sql_096: str, raw_096: str) -> None:
    """Structural idempotency: every seed INSERT uses ON CONFLICT (id) DO NOTHING.

    A live "apply twice" check needs a throwaway Postgres; this WP only asserts the
    SQL shape that makes a second apply a no-op (plus literal id/slug parity with
    tenancy.py).
    """
    system = system_workspace_row()
    house = house_workspace_row()
    assert str(system_workspace_id()) in sql_096
    assert str(house_workspace_id()) in sql_096
    assert f"'{system['slug']}'" in sql_096
    assert f"'{house['slug']}'" in sql_096

    inserts = re.findall(
        r"INSERT\s+INTO\s+public\.workspaces\b.*?;",
        sql_096,
        re.IGNORECASE | re.DOTALL,
    )
    assert len(inserts) == 2, f"expected exactly two workspace seed inserts, got {len(inserts)}"
    for stmt in inserts:
        assert re.search(r"ON\s+CONFLICT\s*\(\s*id\s*\)\s*DO\s+NOTHING", stmt, re.IGNORECASE)

    # Doubling the INSERT block still carries ON CONFLICT DO NOTHING on every copy —
    # structural stand-in for a second apply, without requiring a live database.
    doubled = "\n".join(inserts + inserts)
    assert doubled.count("ON CONFLICT") == 4
    assert "DO NOTHING" in doubled.upper()
    assert "idempotent" in raw_096.lower()


def test_096_skips_k_track_tables_with_comment(raw_096: str, sql_096: str) -> None:
    for name in SKIPPED_K_TRACK:
        assert name in raw_096, f"header must name skipped table {name}"
        assert not re.search(
            rf"CREATE\s+TABLE\s+[^;]*\b{name}\b",
            sql_096,
            re.IGNORECASE,
        ), f"must not CREATE {name} in T0"


def test_096_rls_enabled_and_client_roles_revoked(sql_096: str) -> None:
    for table in (
        "workspaces",
        "workspace_members",
        "stripe_events",
        "job_runs",
        "audit_log",
    ):
        assert re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            sql_096,
            re.IGNORECASE,
        )
        assert re.search(
            rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+[^\n]*\banon\b",
            sql_096,
            re.IGNORECASE,
        )


def test_096_updated_at_trigger(sql_096: str) -> None:
    assert re.search(
        r"CREATE\s+TRIGGER\s+set_updated_at_workspaces\b",
        sql_096,
        re.IGNORECASE,
    )
    assert "trigger_set_updated_at" in sql_096


# ---------------------------------------------------------------------------
# 097 — tenant columns + widened UNIQUEs
# ---------------------------------------------------------------------------


def test_097_adds_workspace_id_to_every_private_set_table(sql_097: str) -> None:
    for table in PRIVATE_SET_TABLES:
        assert re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+workspace_id\s+uuid",
            sql_097,
            re.IGNORECASE,
        ), table
        assert re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ALTER\s+COLUMN\s+workspace_id\s+SET\s+NOT\s+NULL",
            sql_097,
            re.IGNORECASE,
        ), f"{table} must SET NOT NULL after backfill"


def test_097_backfill_order_null_then_fill_then_not_null(sql_097: str) -> None:
    """Binding: NULLable first, backfill, then SET NOT NULL — one migration, explicit steps."""
    for table in ("positions", "portfolio_ledger_commits"):
        add_m = re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+workspace_id",
            sql_097,
            re.IGNORECASE,
        )
        update_m = re.search(
            rf"UPDATE\s+public\.{table}\s+SET\s+workspace_id\s*=",
            sql_097,
            re.IGNORECASE,
        )
        not_null_m = re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ALTER\s+COLUMN\s+workspace_id\s+SET\s+NOT\s+NULL",
            sql_097,
            re.IGNORECASE,
        )
        assert add_m and update_m and not_null_m, table
        assert add_m.start() < update_m.start() < not_null_m.start(), f"{table} step order wrong"


def test_097_group_a_has_house_default_group_b_does_not(sql_097: str) -> None:
    house = str(house_workspace_id())
    # Group A DEFAULT present
    assert re.search(
        rf"positions[\s\S]*?DEFAULT\s+'{house}'::uuid",
        sql_097,
        re.IGNORECASE,
    )
    # Group B: portfolio_ledger_commits ADD COLUMN has no DEFAULT clause
    match = re.search(
        r"ALTER\s+TABLE\s+public\.portfolio_ledger_commits\s+"
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+workspace_id\s+uuid\s*;",
        sql_097,
        re.IGNORECASE,
    )
    assert match, "Group B commits column must be bare uuid (no DEFAULT)"


def test_097_profile_config_house_row_maps_to_system_workspace(sql_097: str) -> None:
    system = str(system_workspace_id())
    assert re.search(
        rf"UPDATE\s+public\.olympus_profile_config\s+"
        rf"SET\s+workspace_id\s+=\s+'{system}'::uuid\s+"
        rf"WHERE\s+workspace_id\s+IS\s+NULL\s+AND\s+is_house_default\s+=\s+true",
        sql_097,
        re.IGNORECASE,
    )


def test_097_temporarily_removes_075_append_only_trigger_for_backfill(sql_097: str) -> None:
    """The schema backfill must not fire migration 075's UPDATE rejection trigger."""
    dropped = sql_097.index("DROP TRIGGER IF EXISTS reject_olympus_profile_config_mutation")
    updated = sql_097.index("UPDATE public.olympus_profile_config")
    recreated = sql_097.index("CREATE TRIGGER reject_olympus_profile_config_mutation")
    assert dropped < updated < recreated
    assert "EXECUTE FUNCTION public.reject_olympus_profile_config_mutation()" in sql_097[recreated:]


def test_097_adds_widened_uniques_alongside_legacy_keys(sql_097: str, raw_097: str) -> None:
    """097 ADDs widened UNIQUEs; must NOT DROP legacy arbiters (live writers still use them)."""
    for token in (
        "uq_positions_workspace_date_ticker",
        "uq_position_events_workspace_date_ticker",
        "uq_nav_history_workspace_date",
        "uq_portfolio_metrics_workspace_date",
        "P6",
    ):
        assert token in raw_097, f"097 header must mention {token}"

    for new_name, cols in ADDED_WIDENED_UNIQUES:
        assert re.search(
            rf"ADD\s+CONSTRAINT\s+{new_name}\s+UNIQUE\s*\(\s*{re.escape(cols)}\s*\)",
            sql_097,
            re.IGNORECASE,
        ), new_name

    # Legacy keys must not be dropped in this WP.
    for legacy in LEGACY_KEYS_KEPT:
        assert not re.search(
            rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{legacy}\b",
            sql_097,
            re.IGNORECASE,
        ), f"must keep legacy arbiter {legacy} until P6"
    assert not re.search(
        r"PRIMARY\s+KEY\s*\(\s*workspace_id\s*,\s*date\s*\)",
        sql_097,
        re.IGNORECASE,
    ), "nav_history PK must stay (date); widened UNIQUE is added beside it"


def test_097_skips_k_track_with_header_comment(raw_097: str, sql_097: str) -> None:
    for name in SKIPPED_K_TRACK:
        assert name in raw_097
        assert not re.search(
            rf"ALTER\s+TABLE\s+public\.{name}\b",
            sql_097,
            re.IGNORECASE,
        )


def test_097_does_not_add_workspace_id_to_corpus_tables(sql_097: str) -> None:
    """Out of scope: corpus / shared research stay tenant-agnostic at the key layer."""
    for table in (
        "olympus_research_corpus",
        "daily_snapshots",
        "documents",
        "theses",
    ):
        assert not re.search(
            rf"ALTER\s+TABLE\s+public\.{table}\s+ADD\s+COLUMN[^;]*workspace_id",
            sql_097,
            re.IGNORECASE,
        ), table


# ---------------------------------------------------------------------------
# 098 — authenticated policies; anon untouched
# ---------------------------------------------------------------------------


def test_098_adds_authenticated_select_policies(sql_098: str) -> None:
    assert re.search(
        r'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+ON\s+public\.workspaces\b',
        sql_098,
        re.IGNORECASE,
    )
    assert re.search(
        r'CREATE\s+POLICY\s+"authenticated_select_own_membership"\s+ON\s+public\.workspace_members\b',
        sql_098,
        re.IGNORECASE,
    )
    for table in PRIVATE_SET_TABLES:
        assert re.search(
            rf'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+ON\s+public\.{table}\b',
            sql_098,
            re.IGNORECASE,
        ), table


def test_098_todo_t5_tier_gate_marker_present(raw_098: str) -> None:
    assert "TODO(T5)" in raw_098


def test_098_private_book_policies_have_no_system_workspace_or(
    sql_098: str,
) -> None:
    """Private-book SELECT policies are own-workspace only — no system OR branch."""
    system_id = "1105372f-4109-5815-be5a-21091ccfc8ad"
    for table in PRIVATE_BOOK_TABLES:
        match = re.search(
            rf'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+'
            rf"ON\s+public\.{table}\b\s+FOR\s+SELECT\s+TO\s+authenticated\s+"
            rf"USING\s*\((.*?)\);",
            sql_098,
            re.IGNORECASE | re.DOTALL,
        )
        assert match, f"missing policy for {table}"
        body = match.group(1)
        assert system_id not in body, f"{table} must not OR system workspace"
        assert "workspace_members" in body

    # System branch retained only on workspaces + olympus_profile_config.
    assert re.search(
        r'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+'
        r"ON\s+public\.workspaces\b[\s\S]*?OR\s+type\s*=\s*'system'",
        sql_098,
        re.IGNORECASE,
    )
    assert re.search(
        rf'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+'
        rf"ON\s+public\.olympus_profile_config\b[\s\S]*?{system_id}",
        sql_098,
        re.IGNORECASE,
    )


def test_no_anon_policy_touched(sql_098: str, raw_098: str) -> None:
    """Binding: this WP must not drop, narrow, or recreate any anon policy."""
    assert not re.search(r"\bTO\s+anon\b", sql_098, re.IGNORECASE)
    assert not re.search(r"DROP\s+POLICY\s+[^;]*anon_read", sql_098, re.IGNORECASE)
    assert not re.search(r"CREATE\s+POLICY\s+[^;]*\banon_read\b", sql_098, re.IGNORECASE)
    for table in ANON_READ_TABLES:
        # Header must name the untouched surfaces so the T1 cutover has a checklist.
        assert table in raw_098
    assert "does NOT drop" in raw_098 or "does not drop" in raw_098.lower()


def test_098_two_jwt_test_plan_documented(raw_098: str) -> None:
    lowered = raw_098.lower()
    assert "two-jwt" in lowered or "two jwt" in lowered
    assert "workspaces a and b" in lowered or "workspace a" in lowered
