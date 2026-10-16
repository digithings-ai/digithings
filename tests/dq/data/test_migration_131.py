"""Unit tests for migration 131 — fx_intraday_observations interval discriminator.

Migration 130 created the twelve-x grading feed keyed ``(source, series_id,
ts)``, which was sound while the writer only emitted 1h bars. A 5m ingest
reuses the same :00 opens, so a 5m upsert would overwrite the 1h row at every
shared instant. Migration 131 adds the ``interval`` column and swaps the
primary key to ``(source, series_id, interval, ts)``.

130 stays immutable (db-migrate.yml ledgers every executed file by basename),
so this file pins both sides: 130 still carries the old key, 131 performs the
guarded replacement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
M131 = MIGRATIONS_DIR / "131_fx_intraday_interval.sql"
M130 = MIGRATIONS_DIR / "130_fx_intraday_observations.sql"

SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

_NEW_PK = re.compile(
    r"ADD CONSTRAINT fx_intraday_observations_pkey\s+"
    r"PRIMARY KEY \(source, series_id, interval, ts\)",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def raw() -> str:
    assert M131.is_file(), f"migration missing: {M131}"
    return M131.read_text(encoding="utf-8")


def test_migration_131_is_only_131_file() -> None:
    assert sorted(MIGRATIONS_DIR.glob("131_*.sql")) == [M131]


def test_single_transaction_compatible(raw: str) -> None:
    """Unwrapped: db-migrate.yml applies file + ledger INSERT atomically."""
    assert SELF_WRAP_REGEX.search(raw) is None
    assert "COMMIT;" not in raw.upper()


def test_interval_column_added_not_null_default_1h(raw: str) -> None:
    assert re.search(
        r"ALTER TABLE public\.fx_intraday_observations\s+"
        r"ADD COLUMN IF NOT EXISTS interval text NOT NULL DEFAULT '1h'",
        raw,
        re.IGNORECASE,
    ), "existing (1h-only) rows must backfill via the column default"


def test_primary_key_swap_is_guarded_and_includes_interval(raw: str) -> None:
    # The old key is dropped only when it is exactly the 130 shape…
    assert "fx_intraday_observations_pkey" in raw
    assert "PRIMARY KEY (source, series_id, ts)" in raw
    # …and the new key includes interval, so 5m and 1h share a ts safely.
    assert _NEW_PK.search(raw)
    # Catalog guards (contype = 'p') make a replay a no-op, not a double-add.
    assert "pg_constraint" in raw
    assert "contype = 'p'" in raw


def test_comments_document_bar_open_interval_and_new_upsert_key(raw: str) -> None:
    assert "COMMENT ON COLUMN public.fx_intraday_observations.interval" in raw
    assert "COMMENT ON COLUMN public.fx_intraday_observations.ts" in raw
    assert "COMMENT ON TABLE public.fx_intraday_observations" in raw
    # The table comment must state the upsert key consumers rely on.
    assert "(source, series_id, interval, ts)" in raw


def test_migration_130_stays_immutable() -> None:
    """131 must not re-edit the applied 130 (new numbered file, same commit)."""
    before = M130.read_text(encoding="utf-8")
    assert "PRIMARY KEY (source, series_id, ts)" in before
    assert "interval text" not in before  # the column is 131-only work
