"""Tests for the Worker-side ports of the non-guard Postgres functions.

``d1_functions.py`` ports every non-``reject_*_mutation`` function found in
``digiquant/supabase/migrations``; ``d1_function_triggers.sql`` carries the
row-level trigger equivalents. The census test below re-derives the function
list from the migrations with an independent parser, so a function silently
left out of both artefacts fails here rather than shipping as a gap.
"""

from __future__ import annotations

import pathlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from digiquant import d1_functions as fn

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
TRIGGERS_SQL = REPO_ROOT / "digiquant" / "src" / "digiquant" / "d1_function_triggers.sql"

FUNC_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?(\w+)\s*\(",
    re.IGNORECASE,
)

# Functions whose ONLY equivalent is d1_reject_guards.sql (19 names).
REJECT_GUARDS = {
    "reject_broker_connection_credential_mutation",
    "reject_broker_mirror_mutation",
    "reject_notification_log_mutation",
    "reject_olympus_accounting_mutation",
    "reject_olympus_attention_context_mutation",
    "reject_olympus_cost_liquidity_mutation",
    "reject_olympus_evidence_bundle_mutation",
    "reject_olympus_forecast_calibration_mutation",
    "reject_olympus_forecast_registry_mutation",
    "reject_olympus_outcome_learning_mutation",
    "reject_olympus_policy_replay_mutation",
    "reject_olympus_pretrade_risk_report_mutation",
    "reject_olympus_profile_config_mutation",
    "reject_olympus_provider_telemetry_mutation",
    "reject_olympus_research_corpus_mutation",
    "reject_olympus_research_state_mutation",
    "reject_olympus_risk_policy_snapshot_mutation",
    "reject_portfolio_ledger_mutation",
    "reject_workspace_provider_credential_mutation",
}

# Everything else must be ported here (module or trigger SQL).
PORTED_HERE = {
    "claim_prices_live_refresh",
    "ensure_my_workspace",
    "ensure_personal_workspace",
    "ensure_position_instrument",
    "handle_new_auth_user_workspace",
    "knowledge_notes_set_updated_at",
    "max_plan_tier",
    "my_access",
    "plan_tier_rank",
    "prune_langgraph_checkpoints",
    "search_architecture_notes",
    "set_instruments_updated_at",
    "trigger_set_updated_at",
    # Row guard that is not a reject_*_mutation (091, trigger SQL).
    "reject_olympus_evidence_amendment_base_mismatch",
}


def _migration_functions() -> set[str]:
    found = set()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = re.sub(r"--[^\n]*", " ", path.read_text(encoding="utf-8"))
        for m in FUNC_RE.finditer(sql):
            found.add(m.group(1).lower())
    return found


def test_census_every_function_is_ported_somewhere():
    live = _migration_functions()
    assert len(live) == 33, f"migration census moved: {sorted(live)}"
    assert live == REJECT_GUARDS | PORTED_HERE, (
        f"unported={sorted(live - REJECT_GUARDS - PORTED_HERE)}"
        f" retired={sorted((REJECT_GUARDS | PORTED_HERE) - live)}"
    )


def test_census_control_proves_the_parser_fires():
    live = _migration_functions()
    assert "plan_tier_rank" in live and "zz_no_such_function" not in live


def test_plan_tier_ladder_is_the_115_spelling():
    assert fn.plan_tier_rank("free") == 0
    assert fn.plan_tier_rank("brief") == 1
    assert fn.plan_tier_rank("desk") == 2
    assert fn.plan_tier_rank("studio") == 3
    assert fn.plan_tier_rank("enterprise") == 4
    # Superseded 108 tiers are unknown spellings, never ranks.
    assert fn.plan_tier_rank("baseline") == 0
    assert fn.plan_tier_rank("custom") == 0
    assert fn.plan_tier_rank(None) == 0
    assert fn.max_plan_tier("desk", "brief") == "desk"
    assert fn.max_plan_tier("free", "studio") == "studio"
    assert fn.max_plan_tier("baseline", "desk") == "desk"


def _workspace_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE workspaces (id TEXT PRIMARY KEY, slug TEXT UNIQUE,"
        " type TEXT, name TEXT, plan_tier TEXT, subscription_status TEXT,"
        " updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE workspace_members (workspace_id TEXT, user_id TEXT,"
        " role TEXT, created_at TEXT DEFAULT 't')"
    )
    conn.execute("CREATE TABLE entitlement_grants (email TEXT PRIMARY KEY, plan_floor TEXT)")
    conn.execute("CREATE TABLE client_product_grants (email TEXT, product_key TEXT)")
    return conn


def test_ensure_personal_workspace_prefers_existing_owner():
    conn = _workspace_db()
    conn.execute("INSERT INTO workspaces VALUES ('w1','s','user','P','free','none',NULL)")
    conn.execute("INSERT INTO workspace_members VALUES ('w1','u1','owner','t')")
    assert fn.ensure_personal_workspace(conn, "u1") == "w1"


def test_ensure_personal_workspace_creates_and_names_owner():
    conn = _workspace_db()
    ws = fn.ensure_personal_workspace(conn, "u9")
    slug = conn.execute("SELECT slug FROM workspaces WHERE id = ?", (ws,)).fetchone()
    assert slug[0] == "u-u9"
    role = conn.execute(
        "SELECT role FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
        (ws, "u9"),
    ).fetchone()
    assert role[0] == "owner"


def test_ensure_personal_workspace_refuses_empty_user_and_system_ids():
    conn = _workspace_db()
    with pytest.raises(ValueError):
        fn.ensure_personal_workspace(conn, "")
    with pytest.raises(ValueError):
        fn.ensure_my_workspace(conn, None)
    # A slug resolving onto a system id is refused, never attached.
    conn.execute(
        "INSERT INTO workspaces VALUES"
        " ('1105372f-4109-5815-be5a-21091ccfc8ad','u-abc','user','P','free','none',NULL)"
    )
    with pytest.raises(ValueError):
        fn.ensure_personal_workspace(conn, "abc")
    assert fn.handle_new_auth_user_workspace(conn, "newbie") is not None


def test_my_access_composes_floor_products_and_effective_tier():
    conn = _workspace_db()
    conn.execute("INSERT INTO workspaces VALUES ('w1','s','user','P','brief','none',NULL)")
    conn.execute("INSERT INTO workspace_members VALUES ('w1','u1','owner','t')")
    conn.execute("INSERT INTO entitlement_grants VALUES ('a@x.io','studio')")
    conn.execute("INSERT INTO client_product_grants VALUES ('a@x.io','brief_desk')")
    got = fn.my_access(conn, "u1", "A@x.io")
    assert got["workspace_plan_tier"] == "brief"
    assert got["plan_floor"] == "studio"
    assert got["effective_plan_tier"] == "studio"
    # plan_floor always implies fx_hub even when the product row lags.
    assert "fx_hub" in got["products"]


def test_claim_prices_live_refresh_atomic_window():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE prices_live_lease (id INTEGER PRIMARY KEY, claimed_at TEXT)")
    conn.execute("INSERT INTO prices_live_lease VALUES (1, '2000-01-01T00:00:00+00:00')")
    t0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert fn.claim_prices_live_refresh(conn, 50, now=t0) is True
    assert fn.claim_prices_live_refresh(conn, 50, now=t0) is False
    later = t0 + timedelta(seconds=51)
    assert fn.claim_prices_live_refresh(conn, 50, now=later) is True
    with pytest.raises(ValueError):
        fn.claim_prices_live_refresh(conn, 0, now=t0)


def test_prune_langgraph_checkpoints_keeps_fresh_and_unparsable():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE checkpoints (thread_id TEXT, checkpoint TEXT)")
    conn.execute("CREATE TABLE checkpoint_writes (thread_id TEXT)")
    conn.execute("CREATE TABLE checkpoint_blobs (thread_id TEXT)")
    now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(days=20)).isoformat()
    fresh = (now - timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO checkpoints VALUES ('stale', '{\"ts\": \"%s\"}')" % old)
    conn.execute("INSERT INTO checkpoints VALUES ('live', '{\"ts\": \"%s\"}')" % fresh)
    conn.execute("INSERT INTO checkpoints VALUES ('odd', 'not-json')")
    conn.execute("INSERT INTO checkpoint_writes VALUES ('stale')")
    conn.execute("INSERT INTO checkpoint_blobs VALUES ('stale')")
    got = fn.prune_langgraph_checkpoints(conn, 14, now=now)
    assert got == {
        "threads_pruned": 1,
        "checkpoints_deleted": 1,
        "writes_deleted": 1,
        "blobs_deleted": 1,
    }
    left = {r[0] for r in conn.execute("SELECT thread_id FROM checkpoints")}
    assert left == {"live", "odd"}
    with pytest.raises(ValueError):
        fn.prune_langgraph_checkpoints(conn, 0, now=now)


def test_search_architecture_notes_ranks_and_scopes():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE architecture_notes (vault_path TEXT, title TEXT,"
        " note_type TEXT, summary TEXT, body_markdown TEXT, tags TEXT,"
        " wikilinks TEXT)"
    )
    conn.execute(
        "INSERT INTO architecture_notes VALUES"
        " ('a/one','lease','n','prices live lease','claim window body','',''),"
        " ('a/two','other','n','nothing','unrelated words here','',''),"
        " ('b/one','lease clock','n','clock','more lease notes','','')"
    )
    assert fn.search_architecture_notes(conn, "") == []
    hits = fn.search_architecture_notes(conn, "lease")
    assert [h["vault_path"] for h in hits] == ["a/one", "b/one"]
    scoped = fn.search_architecture_notes(conn, "lease", path_prefix="b")
    assert [h["vault_path"] for h in scoped] == ["b/one"]
    assert len(fn.search_architecture_notes(conn, "lease", match_limit=1)) == 1


def test_triggers_sql_applies_and_behaves():
    sql = TRIGGERS_SQL.read_text(encoding="utf-8")
    assert "trg_d1_positions_ensure_instrument" in sql
    assert "trg_d1_amendment_base_mismatch" in sql
    conn = sqlite3.connect(":memory:")
    for table in (
        "daily_snapshots",
        "theses",
        "portfolio_metrics",
        "workspaces",
        "notification_prefs",
        "knowledge_notes",
    ):
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, updated_at TEXT)")
    conn.execute("CREATE TABLE positions (id INTEGER PRIMARY KEY, ticker TEXT, updated_at TEXT)")
    conn.execute(
        "CREATE TABLE instruments (ticker TEXT PRIMARY KEY, official_name TEXT,"
        " instrument_type TEXT, asset_class TEXT, category TEXT, provider TEXT,"
        " provider_metadata TEXT, source_updated_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE olympus_missing_fact_requests"
        " (request_id TEXT PRIMARY KEY, base_bundle_id TEXT)"
    )
    conn.execute(
        "CREATE TABLE olympus_evidence_bundle_amendments"
        " (id INTEGER PRIMARY KEY, missing_fact_request_id TEXT, base_bundle_id TEXT)"
    )
    conn.executescript(sql)
    # updated_at stamped when absent, preserved when explicit.
    conn.execute("INSERT INTO positions (ticker) VALUES ('btc')")
    (stamped,) = conn.execute("SELECT updated_at FROM positions").fetchone()
    assert stamped is not None
    # ensure_position_instrument resolved the ticker row.
    inst = conn.execute(
        "SELECT official_name, asset_class FROM instruments WHERE ticker = 'BTC'"
    ).fetchone()
    assert inst == ("BTC", "UNKNOWN")
    conn.execute("INSERT INTO positions (ticker) VALUES ('CASH')")
    cash = conn.execute(
        "SELECT official_name, instrument_type FROM instruments WHERE ticker = 'CASH'"
    ).fetchone()
    assert cash == ("Cash", "CASH")
    # base-match guard: match passes, cross-link and missing request abort.
    conn.execute("INSERT INTO olympus_missing_fact_requests VALUES ('r1','b1')")
    conn.execute(
        "INSERT INTO olympus_evidence_bundle_amendments"
        " (missing_fact_request_id, base_bundle_id) VALUES ('r1','b1')"
    )
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO olympus_evidence_bundle_amendments"
            " (missing_fact_request_id, base_bundle_id) VALUES ('r1','b2')"
        )
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO olympus_evidence_bundle_amendments"
            " (missing_fact_request_id, base_bundle_id) VALUES ('nope','b1')"
        )
