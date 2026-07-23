"""Structural checks for migration 056 thesis topic identity."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "supabase"
    / "migrations"
    / "056_thesis_topic_identity.sql"
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.mark.unit
class TestThesisTopicIdentityMigration:
    def test_adds_and_backfills_topic_key(self, sql: str) -> None:
        assert re.search(r"ADD COLUMN IF NOT EXISTS topic_key\s+text", sql)
        assert re.search(r"UPDATE theses[\s\S]+SET topic_key", sql)

    def test_consolidates_known_live_duplicate_clusters(self, sql: str) -> None:
        assert "cta-risk-management" in sql
        assert "cta-equity-volatility" in sql
        assert "advanced-materials-growth-trend" in sql
        assert "advanced-materials-demand-shift" in sql
        assert "advanced-mat-demand-2026" in sql
        assert "advanced-mat-inflation" in sql

    def test_rewires_relations_before_deleting_duplicate_theses(self, sql: str) -> None:
        vehicle_rewire = sql.index("INSERT INTO thesis_vehicles")
        parent_rewire = sql.index("UPDATE theses\nSET linked_market_thesis_id")
        duplicate_delete = sql.index("DELETE FROM theses")
        assert vehicle_rewire < duplicate_delete
        assert parent_rewire < duplicate_delete
        assert "UPDATE positions" in sql
        assert "UPDATE position_events" in sql
        assert "UPDATE analyst_coverage" in sql

    def test_enforces_one_nonterminal_market_thesis_per_topic_and_date(self, sql: str) -> None:
        assert re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS uq_theses_active_market_topic_date"
            r"[\s\S]+ON theses \(date, topic_key\)"
            r"[\s\S]+thesis_kind = 'market'"
            r"[\s\S]+status NOT IN \('CLOSED', 'INVALIDATED'\)",
            sql,
        )

    def test_is_transactional_with_commented_rollback(self, sql: str) -> None:
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
        assert "Rollback" in sql
        assert "-- DROP INDEX IF EXISTS uq_theses_active_market_topic_date;" in sql


@pytest.mark.unit
def test_vehicle_rewire_deduplicates_before_upsert(sql: str) -> None:
    """Two duplicates collapsing into one canonical must not propose the same
    (date, canonical, ticker) key twice in the single INSERT — Postgres rejects
    ON CONFLICT affecting a row twice (2026-07-23 prod db-migrate failure)."""
    rewire = sql.split("INSERT INTO thesis_vehicles", 1)[1]
    assert "DISTINCT ON (vehicles.date, mapping.canonical_thesis_id, vehicles.ticker)" in rewire
    order_by = re.search(
        r"ORDER BY\s+vehicles\.date,\s*mapping\.canonical_thesis_id,\s*vehicles\.ticker", rewire
    )
    assert order_by, (
        "DISTINCT ON requires a matching ORDER BY prefix to pick a deterministic winner"
    )


@pytest.mark.unit
def test_residual_duplicates_swept_before_unique_index(sql: str) -> None:
    """The enumerated merge map cannot foresee backfill collisions (two live
    theses slugifying to one topic blocked the index in prod, 2026-07-23).
    A computed residual sweep must run after the backfill and before the
    partial unique index, using the index's own predicate."""
    assert "thesis_topic_residual_map" in sql
    backfill = sql.index("'legacy-' || substr(md5(thesis_id), 1, 16)")
    sweep = sql.index("thesis_topic_residual_map")
    index = sql.index("uq_theses_active_market_topic_date")
    assert backfill < sweep < index, "sweep must sit between backfill and index"
    sweep_block = sql[sweep:index]
    assert "NOT IN ('CLOSED', 'INVALIDATED')" in sweep_block, (
        "sweep must mirror the index predicate"
    )
