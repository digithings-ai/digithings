"""Contract tests for migration 069, the private portfolio lineage ledger."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "069_olympus_portfolio_ledger.sql"

TABLES = (
    "portfolio_ledger_commits",
    "portfolio_ledger_decision_intents",
    "portfolio_ledger_requested_targets",
    "portfolio_ledger_target_adjustments",
    "portfolio_ledger_approved_targets",
    "portfolio_ledger_order_intents",
    "portfolio_ledger_paper_executions",
    "portfolio_ledger_holding_lots",
)
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
FORBIDDEN_COLUMNS = (
    "prompt",
    "prompt_body",
    "prompt_content",
    "response",
    "response_body",
    "response_content",
    "message",
    "messages",
    "api_key",
    "secret",
    "raw_exception",
    "search_text",
    "payload",
)
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)


def _strip_comments(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return _strip_comments(raw)


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.{table}\s*"
        rf"\((?P<body>.*?)\)\s*;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing CREATE TABLE for {table}"
    return match.group("body")


def test_migration_is_the_only_069() -> None:
    assert sorted(MIGRATIONS_DIR.glob("069_*.sql")) == [MIGRATION_PATH]


def test_migration_remains_single_transaction_compatible(raw: str) -> None:
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


@pytest.mark.parametrize("table", TABLES)
def test_tables_use_stable_uuid_primary_keys(sql: str, table: str) -> None:
    body = _table_body(sql, table)
    assert re.search(r"\bid\s+uuid\s+PRIMARY KEY\s+DEFAULT\s+gen_random_uuid\(\)", body, re.I)


@pytest.mark.parametrize(
    ("table", "column", "referenced_table"),
    (
        (
            "portfolio_ledger_decision_intents",
            "portfolio_commit_id",
            "portfolio_ledger_commits",
        ),
        (
            "portfolio_ledger_requested_targets",
            "decision_intent_id",
            "portfolio_ledger_decision_intents",
        ),
        (
            "portfolio_ledger_target_adjustments",
            "requested_target_id",
            "portfolio_ledger_requested_targets",
        ),
        (
            "portfolio_ledger_approved_targets",
            "requested_target_id",
            "portfolio_ledger_requested_targets",
        ),
        (
            "portfolio_ledger_order_intents",
            "approved_target_id",
            "portfolio_ledger_approved_targets",
        ),
        (
            "portfolio_ledger_paper_executions",
            "order_intent_id",
            "portfolio_ledger_order_intents",
        ),
        (
            "portfolio_ledger_holding_lots",
            "opened_by_execution_id",
            "portfolio_ledger_paper_executions",
        ),
        (
            "portfolio_ledger_holding_lots",
            "closed_by_execution_id",
            "portfolio_ledger_paper_executions",
        ),
    ),
)
def test_lineage_foreign_keys_point_at_prior_stage(
    sql: str, table: str, column: str, referenced_table: str
) -> None:
    body = _table_body(sql, table)
    assert re.search(
        rf"FOREIGN KEY\s*\({column}\)\s+REFERENCES\s+public\.{referenced_table}",
        body,
        re.IGNORECASE,
    )


@pytest.mark.parametrize(
    ("table", "key_columns"),
    (
        ("portfolio_ledger_commits", "id,\\s*run_date"),
        (
            "portfolio_ledger_approved_targets",
            "id,\\s*run_date,\\s*symbol",
        ),
        (
            "portfolio_ledger_order_intents",
            "id,\\s*run_date,\\s*symbol",
        ),
    ),
)
def test_self_referencing_tables_have_a_lineage_scoped_unique_key(
    sql: str, table: str, key_columns: str
) -> None:
    """The UNIQUE (id, run_date[, symbol]) key backing the composite supersedes_id FK.

    Without this, the composite FK below has nothing to reference: Postgres requires
    a unique or primary key on exactly the referenced column tuple.
    """
    body = _table_body(sql, table)
    assert re.search(rf"UNIQUE\s*\({key_columns}\)", body, re.IGNORECASE)


@pytest.mark.parametrize(
    ("table", "key_columns"),
    (
        ("portfolio_ledger_commits", "run_date"),
        ("portfolio_ledger_approved_targets", "run_date,\\s*symbol"),
        ("portfolio_ledger_order_intents", "run_date,\\s*symbol"),
    ),
)
def test_supersedes_id_is_scoped_to_its_own_lineage_by_composite_fk(
    sql: str, table: str, key_columns: str
) -> None:
    """supersedes_id can only point at a row in the SAME run_date (and symbol, where
    applicable) lineage — enforced by a composite FK, not the plain single-column FK
    used elsewhere in this table. A plain FK would let a supersession link jump
    across run_dates or symbols, corrupting the lineage chain; MATCH SIMPLE (the
    Postgres default for composite FKs) still lets supersedes_id be NULL for a root
    row without requiring every column in the tuple to be non-NULL.
    """
    body = _table_body(sql, table)
    assert re.search(
        rf"FOREIGN KEY\s*\(supersedes_id,\s*{key_columns}\)\s+REFERENCES\s+public\.{table}\s*\(id,\s*{key_columns}\)",
        body,
        re.IGNORECASE,
    )


def test_paper_execution_has_idempotency_unique_constraint(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_paper_executions")
    assert re.search(
        r"UNIQUE\s*\(order_intent_id,\s*executed_date\)",
        body,
        re.IGNORECASE,
    )


@pytest.mark.parametrize("table", TABLES)
def test_recorded_at_is_the_db_write_clock(sql: str, table: str) -> None:
    body = _table_body(sql, table)
    assert re.search(
        r"recorded_at\s+timestamptz\s+NOT NULL\s+DEFAULT\s+now\(\)",
        body,
        re.IGNORECASE,
    )


@pytest.mark.parametrize(
    ("table", "column"),
    (
        ("portfolio_ledger_commits", "effective_at"),
        ("portfolio_ledger_decision_intents", "effective_at"),
        ("portfolio_ledger_requested_targets", "effective_at"),
        ("portfolio_ledger_target_adjustments", "effective_at"),
        ("portfolio_ledger_approved_targets", "effective_at"),
        ("portfolio_ledger_order_intents", "effective_at"),
        ("portfolio_ledger_paper_executions", "executed_at"),
        ("portfolio_ledger_holding_lots", "opened_at"),
    ),
)
def test_producer_supplied_event_time_is_required_and_timezone_aware(
    sql: str, table: str, column: str
) -> None:
    body = _table_body(sql, table)
    assert re.search(rf"\b{column}\s+timestamptz\s+NOT NULL\b", body, re.IGNORECASE)


@pytest.mark.parametrize(
    ("table", "column", "data_type"),
    (
        ("portfolio_ledger_requested_targets", "requested_weight", "numeric"),
        ("portfolio_ledger_requested_targets", "requested_quantity", "numeric"),
        ("portfolio_ledger_approved_targets", "approved_weight", "numeric"),
        ("portfolio_ledger_approved_targets", "approved_quantity", "numeric"),
        ("portfolio_ledger_holding_lots", "closed_at", "timestamptz"),
    ),
)
def test_unknown_economic_values_stay_nullable_never_defaulted(
    sql: str, table: str, column: str, data_type: str
) -> None:
    """Missing weight/quantity/close-time stays NULL; no DEFAULT ever fabricates a value.

    The tail capture spans newlines (re.DOTALL) rather than stopping at the first line
    break: several of these CHECK clauses (e.g. requested_quantity, approved_quantity)
    wrap onto their own lines, and a truncated tail would silently stop inspecting the
    column definition before a DEFAULT written later in it could ever be caught.
    """
    body = _table_body(sql, table)
    definition = re.search(
        rf"\b{column}\s+{data_type}\b(?P<tail>.*?),\n", body, re.IGNORECASE | re.DOTALL
    )
    assert definition, f"missing {column}"
    assert "NOT NULL" not in definition.group("tail").upper()
    assert "DEFAULT" not in definition.group("tail").upper()


@pytest.mark.parametrize(
    ("table", "column"),
    (
        ("portfolio_ledger_order_intents", "quantity"),
        ("portfolio_ledger_paper_executions", "quantity"),
        ("portfolio_ledger_paper_executions", "price"),
        ("portfolio_ledger_holding_lots", "quantity"),
        ("portfolio_ledger_holding_lots", "open_price"),
    ),
)
def test_fill_and_lot_economic_values_are_required_never_zero_coerced(
    sql: str, table: str, column: str
) -> None:
    """A fill/lot quantity or price is NOT NULL, strictly positive, and NaN-excluding —
    absence of a row is the only way to represent "nothing happened", never a
    zero-valued (or NaN, see test_economic_numeric_columns_reject_nan) column."""
    body = _table_body(sql, table)
    definition = re.search(
        rf"\b{column}\s+numeric\s+NOT NULL(?P<tail>.*?),\n", body, re.I | re.DOTALL
    )
    assert definition, f"missing NOT NULL {column} on {table}"
    assert re.search(r">\s*0", definition.group("tail"))
    assert re.search(rf"NOT\s*\(\s*{column}\s*=\s*'NaN'::numeric\s*\)", definition.group("tail"))


def test_target_adjustment_deltas_are_required_and_non_negative(sql: str) -> None:
    """A cap/rounding/carry delta is NOT NULL — the adjustment itself always exists —
    but may legitimately be zero (e.g. a no-op rounding pass), unlike a fill quantity.
    Still excludes NaN: `>= 0` alone does not fail closed against it (see
    test_economic_numeric_columns_reject_nan)."""
    body = _table_body(sql, "portfolio_ledger_target_adjustments")
    for column in ("original_value", "adjusted_value"):
        definition = re.search(
            rf"\b{column}\s+numeric\s+NOT NULL(?P<tail>.*?),\n", body, re.I | re.DOTALL
        )
        assert definition, f"missing NOT NULL {column}"
        assert re.search(r">=\s*0", definition.group("tail"))
        assert re.search(
            rf"NOT\s*\(\s*{column}\s*=\s*'NaN'::numeric\s*\)", definition.group("tail")
        )


@pytest.mark.parametrize(
    ("table", "column"),
    (
        ("portfolio_ledger_requested_targets", "requested_quantity"),
        ("portfolio_ledger_target_adjustments", "original_value"),
        ("portfolio_ledger_target_adjustments", "adjusted_value"),
        ("portfolio_ledger_approved_targets", "approved_quantity"),
        ("portfolio_ledger_order_intents", "quantity"),
        ("portfolio_ledger_paper_executions", "quantity"),
        ("portfolio_ledger_paper_executions", "price"),
        ("portfolio_ledger_holding_lots", "quantity"),
        ("portfolio_ledger_holding_lots", "open_price"),
    ),
)
def test_economic_numeric_columns_reject_nan(sql: str, table: str, column: str) -> None:
    """Postgres `numeric` treats NaN as equal to itself and greater than every other
    value, so `'NaN'::numeric > 0` and `'NaN'::numeric >= 0` are both TRUE — a bare
    `> 0`/`>= 0` CHECK does not fail closed against it the way an IEEE float would.
    Every economically meaningful numeric column in this migration must carry an
    explicit `NOT (column = 'NaN'::numeric)` guard alongside its positivity/
    non-negativity CHECK. (Weight columns are exempt: `NaN BETWEEN 0 AND 1` is
    already false, so they reject NaN "by accident" with no extra guard needed.)"""
    body = _table_body(sql, table)
    normalized = " ".join(body.split())
    assert f"NOT ({column} = 'NaN'::numeric)" in normalized, (
        f"{table}.{column} is missing the explicit NaN guard"
    )


@pytest.mark.parametrize(
    ("table", "column"),
    (
        ("portfolio_ledger_requested_targets", "requested_quantity"),
        ("portfolio_ledger_target_adjustments", "original_value"),
        ("portfolio_ledger_target_adjustments", "adjusted_value"),
        ("portfolio_ledger_approved_targets", "approved_quantity"),
        ("portfolio_ledger_order_intents", "quantity"),
        ("portfolio_ledger_paper_executions", "quantity"),
        ("portfolio_ledger_paper_executions", "price"),
        ("portfolio_ledger_holding_lots", "quantity"),
        ("portfolio_ledger_holding_lots", "open_price"),
    ),
)
def test_economic_numeric_columns_reject_infinity(sql: str, table: str, column: str) -> None:
    """Postgres `numeric` also admits `'Infinity'::numeric` (and `-Infinity`), and it
    passes the same positivity/non-negativity CHECKs an IEEE float's infinity would
    fail closed against: `'Infinity'::numeric > 0` and `>= 0` are both TRUE. Every
    economically meaningful numeric column in this migration must carry an explicit
    `NOT (column = 'Infinity'::numeric)` guard alongside its NaN guard. (Weight
    columns are exempt: `Infinity BETWEEN 0 AND 1` is already false, so they reject
    Infinity "by accident" with no extra guard needed.)"""
    body = _table_body(sql, table)
    normalized = " ".join(body.split())
    assert f"NOT ({column} = 'Infinity'::numeric)" in normalized, (
        f"{table}.{column} is missing the explicit Infinity guard"
    )


@pytest.mark.parametrize(
    ("table", "column", "values"),
    (
        (
            "portfolio_ledger_decision_intents",
            "action",
            ("add", "trim", "exit", "no_op", "reject"),
        ),
        (
            "portfolio_ledger_decision_intents",
            "reason",
            (
                "new_conviction",
                "conviction_reduced",
                "thesis_invalidated",
                "no_signal_change",
                "risk_cap_breach",
                "low_conviction",
                "data_unavailable",
            ),
        ),
        (
            "portfolio_ledger_target_adjustments",
            "adjustment_type",
            ("cap", "rounding", "carry"),
        ),
        (
            "portfolio_ledger_order_intents",
            "status",
            ("pending", "executed", "rejected"),
        ),
        (
            "portfolio_ledger_order_intents",
            "rejection_reason",
            (
                "risk_limit",
                "insufficient_cash",
                "stale_target",
                "market_closed",
                "data_unavailable",
            ),
        ),
        ("portfolio_ledger_holding_lots", "status", ("open", "closed")),
    ),
)
def test_state_columns_are_closed(
    sql: str, table: str, column: str, values: tuple[str, ...]
) -> None:
    """Matches both the plain `CHECK (column IN (...))` form used by every required
    closed-vocabulary column and the `column IS NULL OR column IN (...)` form used by
    the one nullable one (order_intents.rejection_reason)."""
    body = _table_body(sql, table)
    match = re.search(rf"{column}\s+IN\s*\((?P<values>.*?)\)", body, re.I | re.S)
    assert match, f"missing closed CHECK for {table}.{column}"
    assert set(re.findall(r"'([^']+)'", match.group("values"))) == set(values)


def test_decision_action_reason_pairing_is_enforced(sql: str) -> None:
    """reason is NOT NULL for every action (including no_op/reject) and is cross-checked
    so a technically-non-null reason still cannot pair with an unrelated action."""
    body = _table_body(sql, "portfolio_ledger_decision_intents")
    normalized = " ".join(body.split())
    assert "reason text NOT NULL" in normalized
    assert "action = 'add' AND reason = 'new_conviction'" in normalized
    assert "action = 'no_op' AND reason IN ('no_signal_change', 'data_unavailable')" in normalized
    assert (
        "action = 'reject' AND reason IN ('risk_cap_breach', 'low_conviction', 'data_unavailable')"
    ) in normalized


def test_requested_targets_require_exactly_one_value(sql: str) -> None:
    """requested_targets is XOR, not OR: a row carrying both weight and quantity would
    leave every downstream target_adjustments row against it dimensionally ambiguous."""
    body = _table_body(sql, "portfolio_ledger_requested_targets")
    normalized = " ".join(body.split())
    assert ("(requested_weight IS NOT NULL) <> (requested_quantity IS NOT NULL)") in normalized


def test_approved_targets_require_at_least_one_value(sql: str) -> None:
    """approved_targets is OR, not XOR: unlike requested_targets, nothing downstream of
    an approved target infers a unit from which column is populated, so both may be set."""
    body = _table_body(sql, "portfolio_ledger_approved_targets")
    normalized = " ".join(body.split())
    assert "approved_weight IS NOT NULL OR approved_quantity IS NOT NULL" in normalized


def test_cap_adjustment_can_only_reduce_value(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_target_adjustments")
    normalized = " ".join(body.split())
    assert "adjustment_type <> 'cap' OR adjusted_value <= original_value" in normalized


def test_commit_supersession_is_self_reference_safe(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_commits")
    normalized = " ".join(body.split())
    assert "supersedes_id IS NULL OR supersedes_id <> id" in normalized


def test_approved_target_supersession_is_self_reference_safe(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_approved_targets")
    normalized = " ".join(body.split())
    assert "supersedes_id IS NULL OR supersedes_id <> id" in normalized


def test_order_intent_supersession_is_self_reference_safe(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_order_intents")
    normalized = " ".join(body.split())
    assert "supersedes_id IS NULL OR supersedes_id <> id" in normalized


def test_order_intent_rejection_reason_is_tied_to_status(sql: str) -> None:
    """rejection_reason is populated iff status is 'rejected' — the only axis tied to
    status. supersedes_id is orthogonal (see
    test_order_intent_supersession_is_self_reference_safe above) and never appears in
    this CHECK; an executed row is terminal because append-only forbids the UPDATE and
    the PRIMARY KEY forbids re-INSERTing the same id, not because of this constraint."""
    body = _table_body(sql, "portfolio_ledger_order_intents")
    normalized = " ".join(body.split())
    assert ("status = 'rejected' AND rejection_reason IS NOT NULL") in normalized
    assert ("status <> 'rejected' AND rejection_reason IS NULL") in normalized


@pytest.mark.parametrize(
    ("index_name", "table", "columns", "where_clause"),
    (
        (
            "uq_portfolio_ledger_commits_one_root",
            "portfolio_ledger_commits",
            "run_date",
            "supersedes_id IS NULL",
        ),
        (
            "uq_portfolio_ledger_commits_supersedes",
            "portfolio_ledger_commits",
            "supersedes_id",
            "supersedes_id IS NOT NULL",
        ),
        (
            "uq_portfolio_ledger_approved_targets_one_root",
            "portfolio_ledger_approved_targets",
            "run_date, symbol",
            "supersedes_id IS NULL",
        ),
        (
            "uq_portfolio_ledger_approved_targets_supersedes",
            "portfolio_ledger_approved_targets",
            "supersedes_id",
            "supersedes_id IS NOT NULL",
        ),
        (
            "uq_portfolio_ledger_order_intents_one_root",
            "portfolio_ledger_order_intents",
            "run_date, symbol",
            "supersedes_id IS NULL",
        ),
        (
            "uq_portfolio_ledger_order_intents_supersedes",
            "portfolio_ledger_order_intents",
            "supersedes_id",
            "supersedes_id IS NOT NULL",
        ),
    ),
)
def test_currency_partial_unique_indexes(
    sql: str, index_name: str, table: str, columns: str, where_clause: str
) -> None:
    """These partial UNIQUE indexes are the literal OLY-REV-009 fix: "at most one
    current row" has no WHERE clause under a table CONSTRAINT, so currency (one root
    per key, at most one superseder per row) is enforced here instead of via a status
    column."""
    assert re.search(
        rf"CREATE UNIQUE INDEX IF NOT EXISTS {re.escape(index_name)}\s+"
        rf"ON public\.{table}\s*\({re.escape(columns)}\)\s+WHERE\s+{re.escape(where_clause)};",
        sql,
        re.IGNORECASE,
    ), f"missing or malformed {index_name}"


def test_order_intent_one_root_index_admits_a_superseding_replacement(sql: str) -> None:
    """Regression coverage for the OLY-REV-009-adjacent bug this predicate closes:
    the original index scoped its predicate to `status = 'pending' AND supersedes_id
    IS NULL`. supersedes_id is orthogonal to status (see
    test_order_intent_supersession_is_self_reference_safe) and append-only immutability
    means a superseded row can never leave 'pending' on its own, so that predicate
    would collide a superseding replacement (also inserted as 'pending') with the
    stale row it is meant to replace — silently blocking the documented supersession
    flow whenever the pending currency window spans a same-day correction, exactly
    the OLY-REV-009 scenario for the sibling commits/approved_targets tables.

    The fix drops the `status` predicate entirely and scopes to `supersedes_id IS
    NULL` alone, matching the pattern already used by
    uq_portfolio_ledger_commits_one_root and uq_portfolio_ledger_approved_targets_one_root:
    only the *root* row (no predecessor) is covered by the uniqueness rule, so a
    replacement — which always has `supersedes_id` set — is exempt from it and free
    to coexist with the row it supersedes, regardless of either row's `status`."""
    match = re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS uq_portfolio_ledger_order_intents_one_root\s+"
        r"ON public\.portfolio_ledger_order_intents\s*\(run_date, symbol\)\s+WHERE\s+([^;]+);",
        sql,
        re.IGNORECASE,
    )
    assert match, "missing or malformed uq_portfolio_ledger_order_intents_one_root"
    predicate = " ".join(match.group(1).split())
    assert predicate.strip() == "supersedes_id IS NULL", (
        "the one-root index must scope to supersedes_id IS NULL only — reintroducing "
        "a status predicate would let a superseding replacement order collide with "
        "the stale pending row it replaces"
    )


def test_holding_lot_lifecycle_ties_closed_fields_to_status(sql: str) -> None:
    body = _table_body(sql, "portfolio_ledger_holding_lots")
    normalized = " ".join(body.split())
    assert (
        "status = 'open' AND closed_at IS NULL AND closed_by_execution_id IS NULL"
    ) in normalized
    assert (
        "status = 'closed' AND closed_at IS NOT NULL AND closed_by_execution_id IS NOT NULL"
    ) in normalized
    assert "closed_at IS NULL OR closed_at >= opened_at" in normalized
    assert (
        "closed_by_execution_id IS NULL OR closed_by_execution_id <> opened_by_execution_id"
    ) in normalized


def test_schema_has_no_payload_or_secret_columns(sql: str) -> None:
    bodies = "\n".join(_table_body(sql, table) for table in TABLES)
    for forbidden in FORBIDDEN_COLUMNS:
        assert not re.search(
            rf"^\s*{forbidden}\s+",
            bodies,
            re.IGNORECASE | re.MULTILINE,
        )


@pytest.mark.parametrize("table", TABLES)
def test_tables_are_private(sql: str, table: str) -> None:
    assert re.search(
        rf"ALTER TABLE public\.{table} ENABLE ROW LEVEL SECURITY;",
        sql,
        re.IGNORECASE,
    )
    assert not re.search(rf"CREATE\s+POLICY[^;]*ON\s+public\.{table}", sql, re.I | re.S)
    revoke = re.search(rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+([^;]+);", sql, re.I)
    assert revoke, f"missing complete client revoke for {table}"
    revoked_roles = {role.strip() for role in revoke.group(1).split(",")}
    assert revoked_roles == set(PUBLIC_ROLES)


@pytest.mark.parametrize("table", TABLES)
def test_service_role_can_only_insert_and_read(sql: str, table: str) -> None:
    revoke = re.search(
        rf"REVOKE\s+ALL\s+ON\s+public\.{table}\s+FROM\s+service_role;",
        sql,
        re.IGNORECASE,
    )
    grant = re.search(
        rf"GRANT\s+(?P<privileges>[^;]+?)\s+ON\s+public\.{table}\s+TO\s+service_role;",
        sql,
        re.IGNORECASE,
    )
    assert revoke, f"missing service_role reset for {table}"
    assert grant, f"missing service_role grant for {table}"
    assert revoke.end() < grant.start(), (
        f"service_role privileges are not reset before {table} grant"
    )
    privileges = {item.strip().upper() for item in grant.group("privileges").split(",")}
    assert privileges == {"SELECT", "INSERT"}


@pytest.mark.parametrize("table", TABLES)
def test_mutation_rejection_trigger_guards_each_table(sql: str, table: str) -> None:
    assert re.search(
        rf"CREATE TRIGGER reject_{table}_mutation\s+BEFORE UPDATE OR DELETE\s+"
        rf"ON public\.{table}",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        rf"CREATE TRIGGER reject_{table}_truncate\s+BEFORE TRUNCATE\s+"
        rf"ON public\.{table}\s+FOR EACH STATEMENT",
        sql,
        re.IGNORECASE | re.DOTALL,
    )


def test_mutation_trigger_function_is_shared_and_always_raises(sql: str) -> None:
    """One function, reused by all eight tables (mirroring 067's own naming pattern),
    always raises regardless of statement — there is no code path where it returns.

    The body assertion checks both that it raises AND that it contains no RETURN at
    all (the actual function body is a single unconditional RAISE EXCEPTION with no
    branching) — "RAISE EXCEPTION is present" alone would also pass for a function
    that only raises conditionally on some branches and returns normally on others.
    """
    function = re.search(
        r"CREATE OR REPLACE FUNCTION public\.reject_portfolio_ledger_mutation\(\)"
        r".*?\$\$(?P<body>.*?)\$\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert function
    assert "RAISE EXCEPTION" in function.group("body").upper()
    assert "RETURN" not in function.group("body").upper()
    for table in TABLES:
        # The always-true "DROP TRIGGER IF EXISTS ..._truncate follows" adjacency check
        # that used to sit in an `or` with this pattern is deliberately not here: that
        # branch matches for every table purely from construction order, regardless of
        # whether FOR EACH ROW is actually tied to the mutation trigger, which made the
        # real assertion below dead code. Assert only the real thing.
        assert re.search(
            rf"BEFORE UPDATE OR DELETE ON public\.{table}\s+"
            rf"FOR EACH ROW EXECUTE FUNCTION public\.reject_portfolio_ledger_mutation\(\)",
            sql,
            re.IGNORECASE,
        ), f"missing row-level mutation trigger for {table}"


def test_mutation_trigger_function_is_revoked_from_client_roles(sql: str) -> None:
    revoke = re.search(
        r"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.reject_portfolio_ledger_mutation\(\)\s+"
        r"FROM\s+([^;]+);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert revoke, "missing client-role revoke on the shared trigger function"
    revoked_roles = {role.strip() for role in re.split(r",|\n", revoke.group(1)) if role.strip()}
    assert revoked_roles == set(PUBLIC_ROLES)
