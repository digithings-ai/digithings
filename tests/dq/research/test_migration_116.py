"""Contract tests for migration 116 — authenticated read parity with anon.

The defect 116 closes is silent by construction: RLS enabled + a SELECT grant to
``authenticated`` + no policy for that role yields zero rows, which PostgREST
returns as ``200 []``. There is no error to catch and no log line, so the only
durable guard is a static one over the migration set — hence this file.

``test_no_anon_select_without_authenticated_counterpart`` is the part that earns
its keep: it fails the next time a migration opens a table to ``anon`` and
forgets the signed-in role, which is exactly how 109 left eighteen tables
half-open for three days.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "116_authenticated_read_public_reference.sql"

POLICY_NAME = "authenticated_read_public_reference"

# The eighteen tables that had an anon SELECT policy and no authenticated one.
EXPECTED_TABLES = (
    "analyst_coverage",
    "architecture_notes",
    "current_book_lookback",
    "decision_log",
    "deep_dive_triggers",
    "deliberation_rounds",
    "deliberation_sessions",
    "fx_economic_calendar",
    "macro_series_observations",
    "onchain_cohort_positioning",
    "portfolio_holdings_daily",
    "portfolio_lots",
    "portfolio_trades",
    "price_history",
    "price_technicals",
    "strategy_tearsheets",
    "thesis_vehicles",
    "trading_calendar",
)

# Deliberately anon-denied. A future edit that sweeps these into the mirror
# would hand every signed-in free account the private book.
MUST_NOT_APPEAR = (
    "atlas_run_diagnostics",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
    "strategy_calibrations",
    "portfolio_ledger_commits",
    "portfolio_ledger_holding_lots",
    "portfolio_ledger_paper_executions",
    "olympus_accounting_periods",
    "olympus_accounting_holdings",
    "olympus_accounting_contributions",
    "workspaces",
    "workspace_members",
    "workspace_provider_credentials",
    "broker_connections",
    "entitlement_grants",
)

# Tables whose anon SELECT policy intentionally has no authenticated twin.
# Empty today: every such table either got a twin in 109/114/116 or is
# anon-denied outright. Add an entry only with the reason it is safe.
PARITY_EXEMPT: dict[str, str] = {}

_CREATE_POLICY = re.compile(
    r'CREATE\s+POLICY\s+"?(?P<name>[\w ]+)"?\s+ON\s+(?:public\.)?(?P<table>\w+)'
    r"(?P<body>.*?);",
    re.IGNORECASE | re.DOTALL,
)
_DROP_POLICY = re.compile(
    r'DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?"?(?P<name>[\w ]+)"?\s+ON\s+(?:public\.)?(?P<table>\w+)',
    re.IGNORECASE,
)
_FOR_CMD = re.compile(r"\bFOR\s+(SELECT|INSERT|UPDATE|DELETE|ALL)\b", re.IGNORECASE)
_TO_ROLES = re.compile(r"\bTO\s+(?P<roles>[\w\s,]+?)(?=\s+(?:USING|WITH)\b)", re.IGNORECASE)
# Policies live on tables. Dropping the table, or replacing it with a view,
# retires them — 010 drops benchmark_history, 073 turns position_attribution
# into a view. Without these the replay reports both as permanent orphans.
_DROP_TABLE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?P<table>\w+)", re.IGNORECASE
)
_CREATE_VIEW = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:public\.)?(?P<table>\w+)",
    re.IGNORECASE,
)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def test_targets_exactly_the_expected_tables(sql: str) -> None:
    created = {m.group("table") for m in _CREATE_POLICY.finditer(sql)}
    assert created == set(EXPECTED_TABLES)


def test_every_policy_is_select_to_authenticated(sql: str) -> None:
    for match in _CREATE_POLICY.finditer(sql):
        body = match.group("body")
        table = match.group("table")
        assert match.group("name").strip() == POLICY_NAME, table
        cmd = _FOR_CMD.search(body)
        assert cmd and cmd.group(1).upper() == "SELECT", f"{table} is not FOR SELECT"
        roles = _TO_ROLES.search(body)
        assert roles, f"{table} has no TO clause"
        assert [r.strip() for r in roles.group("roles").split(",")] == ["authenticated"], table


def test_is_idempotent(sql: str) -> None:
    """Every CREATE is preceded by a DROP IF EXISTS on the same table."""
    dropped = {
        m.group("table") for m in _DROP_POLICY.finditer(sql) if "IF EXISTS" in m.group(0).upper()
    }
    created = {m.group("table") for m in _CREATE_POLICY.finditer(sql)}
    assert created - dropped == set()


def test_does_not_open_private_surfaces(sql: str) -> None:
    created = {m.group("table") for m in _CREATE_POLICY.finditer(sql)}
    assert created.isdisjoint(MUST_NOT_APPEAR)


def test_no_anon_select_without_authenticated_counterpart() -> None:
    """No applied migration may leave a table anon-readable but authenticated-blind.

    Replays every top-level migration in filename order (the order
    ``db-migrate.yml`` applies them) and diffs the surviving SELECT policies per
    role. ``migrations/cutover/`` is excluded — that subdirectory is never
    executed by the apply loop.
    """
    anon: dict[str, set[str]] = {}
    authed: dict[str, set[str]] = {}

    def retire(table: str) -> None:
        anon.pop(table, None)
        authed.pop(table, None)

    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        body = _strip_comments(path.read_text(encoding="utf-8"))
        for match in _DROP_TABLE.finditer(body):
            retire(match.group("table"))
        for match in _CREATE_VIEW.finditer(body):
            retire(match.group("table"))
        for match in _DROP_POLICY.finditer(body):
            name, table = match.group("name").strip(), match.group("table")
            anon.get(table, set()).discard(name)
            authed.get(table, set()).discard(name)
        for match in _CREATE_POLICY.finditer(body):
            cmd = _FOR_CMD.search(match.group("body"))
            if not cmd or cmd.group(1).upper() not in {"SELECT", "ALL"}:
                continue
            roles_match = _TO_ROLES.search(match.group("body"))
            if not roles_match:
                continue
            roles = {r.strip().lower() for r in roles_match.group("roles").split(",")}
            name, table = match.group("name").strip(), match.group("table")
            if "anon" in roles:
                anon.setdefault(table, set()).add(name)
            if "authenticated" in roles:
                authed.setdefault(table, set()).add(name)

    orphans = sorted(
        table
        for table, names in anon.items()
        if names and not authed.get(table) and table not in PARITY_EXEMPT
    )
    assert not orphans, (
        "These tables grant SELECT to anon but have no authenticated policy. "
        "A signed-in user reads zero rows and PostgREST reports 200 []: "
        f"{orphans}"
    )
