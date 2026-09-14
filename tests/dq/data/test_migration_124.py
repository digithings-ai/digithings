"""Unit tests for migration 124 — market-data table drop (DEFERRED, #3951).

History: #3780/#3840 landed this migration as the R2 cutover's point of no
return, dropping Supabase ``price_history`` + ``price_technicals`` once reads
were routed via R2 and parity was green. The on-cron Supabase readers were not
actually migrated, so #3951 defers the irreversible DROP: the tables are
retained until those readers have R2 seams with tests. These tests therefore
assert the *deferral*, not the drop.

Ruling 2026-09-09 (macro carve-out): ``macro_series_observations`` STAYS —
fedprob/bitview series still have no R2 home, so this migration must neither
drop it nor gate on it.

The size gate below asserts the gate LOGIC (threshold constant + pass/fail
computation) only. The live byte count (``SELECT pg_database_size`` before /
after DROP / after VACUUM) is an operator run owned by Task 10.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M124 = MIGRATIONS_DIR / "124_drop_market_data_tables.sql"
M121 = MIGRATIONS_DIR / "121_checkpoint_blobs_nullable.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)
_DROP_TABLE = re.compile(
    r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:public\.)?(?P<table>\w+)", re.IGNORECASE
)
_LINE_COMMENT = re.compile(r"--[^\n]*")

DEFERRED_TABLES = ("price_history", "price_technicals")


def _strip_line_comments(raw: str) -> str:
    """SQL active statements only — commented-out DROPs must not read as active."""
    return _LINE_COMMENT.sub("", raw)


@pytest.fixture(scope="module")
def raw() -> str:
    assert M124.is_file(), f"migration missing: {M124}"
    return M124.read_text(encoding="utf-8")


def test_migration_124_is_only_124_file() -> None:
    assert sorted(MIGRATIONS_DIR.glob("124_*.sql")) == [M124]


def test_header_convention_matches_119_to_121(raw: str) -> None:
    """First-six-line shape must match 121 exactly, modulo the filename."""
    prior = M121.read_text(encoding="utf-8").splitlines()
    lines = raw.splitlines()
    assert lines[0] == f"-- {M124.name}"
    assert lines[1:6] == prior[1:6]


def test_single_transaction_compatible(raw: str) -> None:
    """Unwrapped: db-migrate.yml applies file + ledger INSERT atomically."""
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_no_active_drop_before_on_cron_readers_are_migrated(raw: str) -> None:
    """#3951: the DROPs are deferred — no active DROP TABLE remains.

    The real drop is a FUTURE NUMBERED FILE (e.g. ``126_drop_market_data_tables.sql``),
    never a re-edit of 124: db-migrate.yml ledgers every executed file by basename,
    so once this no-op runs a re-edited 124 is silently skipped as "already applied".
    """
    active = _strip_line_comments(raw)
    assert _DROP_TABLE.search(active) is None, "DROP must stay commented/removed"
    # The deferred point-of-no-return must remain discoverable, not silently gone.
    for table in DEFERRED_TABLES:
        assert table in raw, f"{table} deferral rationale must be documented"
    assert "#3951" in raw, "deferral must link the follow-up that unblocks it"
    assert "DIGIQUANT_MARKET_DATA_BACKEND=r2" in raw
    # The header must warn against re-editing 124 and name a new numbered file.
    assert "NEW numbered migration" in raw
    assert "do NOT un-comment" in raw


def test_macro_table_carve_out(raw: str) -> None:
    """macro_series_observations is documented but never dropped or gated."""
    assert "macro_series_observations" in raw.lower(), "carve-out ruling must be documented"
    for match in _DROP_TABLE.finditer(raw):
        assert match.group("table").lower() != "macro_series_observations"


def test_size_gate_threshold_is_320mb() -> None:
    from digiquant.data.cutover_gate import POST_CUTOVER_SIZE_GATE_MB

    assert POST_CUTOVER_SIZE_GATE_MB == 320


def test_size_gate_pass_fail_computation() -> None:
    from digiquant.data.cutover_gate import (
        POST_CUTOVER_SIZE_GATE_MB,
        cutover_size_gate_passes,
    )

    gate_bytes = POST_CUTOVER_SIZE_GATE_MB * 1024 * 1024
    assert cutover_size_gate_passes(gate_bytes) is True
    assert cutover_size_gate_passes(gate_bytes - 1) is True
    assert cutover_size_gate_passes(gate_bytes + 1) is False
