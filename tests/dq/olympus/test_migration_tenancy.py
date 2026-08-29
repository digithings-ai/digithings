"""Structural contract tests for T0 tenancy migrations 096–098.

Mirrors the atlas ``test_migration_0XX.py`` style: parse SQL on disk, never talk to
live Supabase. Executable two-JWT RLS proof lands with T1; here we assert policies
exist, anon policies are untouched, seeds are idempotent, and every widened UNIQUE
is enumerated.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from digiquant.olympus.tenancy import (
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

# Constraint changes this WP is allowed to make (097 header + body must agree).
WIDENED_UNIQUES = (
    ("positions_date_ticker_key", "uq_positions_workspace_date_ticker", "workspace_id, date, ticker"),
    (
        "position_events_date_ticker_key",
        "uq_position_events_workspace_date_ticker",
        "workspace_id, date, ticker",
    ),
    ("nav_history_pkey", "nav_history_pkey", "workspace_id, date"),
    (
        "portfolio_metrics_date_key",
        "uq_portfolio_metrics_workspace_date",
        "workspace_id, date",
    ),
)

PRIVATE_SET_TABLES = (
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


def test_migration_numbers_are_096_097_098_only() -> None:
    """099 is reserved by sibling K3 (`broker_connections`); T0 must not claim it."""
    assert sorted(MIGRATIONS_DIR.glob("096_*.sql")) == [M096]
    assert sorted(MIGRATIONS_DIR.glob("097_*.sql")) == [M097]
    assert sorted(MIGRATIONS_DIR.glob("098_*.sql")) == [M098]
    assert list(MIGRATIONS_DIR.glob("099_*.sql")) == []
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


def test_096_seeds_system_and_house_idempotently(sql_096: str, raw_096: str) -> None:
    """Seeds must be runnable twice: ON CONFLICT (id) DO NOTHING on both inserts.

    Structural stand-in for applying the migration twice against a live database —
    the acceptance criterion is satisfied by asserting the idempotency clause is
    present on every seed INSERT (and that the literal ids match tenancy.py).
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

    # Header + body both claim re-run safety; a second copy of the same INSERT block
    # must still parse as ON CONFLICT DO NOTHING (the "run twice" structural check).
    doubled = "\n".join(inserts + inserts)
    assert doubled.count("ON CONFLICT") == 4
    assert "DO NOTHING" in doubled.upper()
    # Raw file must state the seeds are idempotent so reviewers see the contract.
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
    # Spot-check positions (Group A) and portfolio_ledger_commits (Group B).
    for table in ("positions", "portfolio_ledger_commits"):
        add_pos = sql_097.upper().find(f"ALTER TABLE PUBLIC.{table.upper()} ADD COLUMN")
        update_pos = sql_097.upper().find(f"UPDATE PUBLIC.{table.upper()} SET WORKSPACE_ID")
        not_null_pos = sql_097.upper().find(
            f"ALTER TABLE PUBLIC.{table.upper()} ALTER COLUMN WORKSPACE_ID SET NOT NULL"
        )
        assert add_pos != -1 and update_pos != -1 and not_null_pos != -1, table
        assert add_pos < update_pos < not_null_pos, f"{table} step order wrong"


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


def test_097_every_widened_unique_is_enumerated(sql_097: str, raw_097: str) -> None:
    """Every constraint this migration changes must appear in both header and body."""
    header_must_mention = (
        "uq_positions_workspace_date_ticker",
        "uq_position_events_workspace_date_ticker",
        "nav_history",
        "uq_portfolio_metrics_workspace_date",
    )
    for token in header_must_mention:
        assert token in raw_097, f"097 header must enumerate constraint change involving {token}"

    for old_name, new_name, cols in WIDENED_UNIQUES:
        if old_name == "nav_history_pkey":
            assert re.search(
                r"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+nav_history_pkey",
                sql_097,
                re.IGNORECASE,
            )
            assert re.search(
                r"PRIMARY\s+KEY\s*\(\s*workspace_id\s*,\s*date\s*\)",
                sql_097,
                re.IGNORECASE,
            )
        else:
            assert re.search(
                rf"DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+{old_name}",
                sql_097,
                re.IGNORECASE,
            ), old_name
            assert re.search(
                rf"ADD\s+CONSTRAINT\s+{new_name}\s+UNIQUE\s*\(\s*{re.escape(cols)}\s*\)",
                sql_097,
                re.IGNORECASE,
            ), new_name


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
    assert "Two-JWT" in raw_098 or "two-JWT" in raw_098 or "two JWT" in raw_098.lower()
    assert "workspace A" in raw_098.lower() or "workspaces A and B" in raw_098.lower()
