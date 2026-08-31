"""Structural contract tests for staged cutover 900 (not auto-applied)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CUTOVER_PATH = (
    REPO_ROOT
    / "digiquant"
    / "supabase"
    / "migrations"
    / "cutover"
    / "900_drop_anon_read_cutover.sql"
)
HOUSE_UUID = "6b753576-ced9-5319-9bfa-c5d0aacd9319"
BOOK_TABLES = ("positions", "position_events", "nav_history", "portfolio_metrics")


@pytest.fixture(scope="module")
def raw() -> str:
    assert CUTOVER_PATH.is_file(), f"cutover missing: {CUTOVER_PATH}"
    return CUTOVER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def _policy_body(sql: str, table: str) -> str:
    match = re.search(
        rf'CREATE\s+POLICY\s+"authenticated_select_own_workspace"\s+'
        rf"ON\s+public\.{table}\b([\s\S]*?);",
        sql,
        re.I,
    )
    assert match, f"missing membership policy for {table}"
    return match.group(1)


def test_cutover_stays_under_cutover_dir() -> None:
    assert CUTOVER_PATH.parent.name == "cutover"
    top_level = list((REPO_ROOT / "digiquant" / "supabase" / "migrations").glob("900_*.sql"))
    assert top_level == []


def test_reverts_109_house_uuid_on_book_tables(sql: str) -> None:
    for table in BOOK_TABLES:
        body = _policy_body(sql, table)
        assert "workspace_members" in body
        assert "auth.uid()" in body
        assert HOUSE_UUID not in body, table


def test_drops_daily_snapshots_authenticated_teaser(sql: str) -> None:
    assert re.search(
        r'DROP\s+POLICY\s+IF\s+EXISTS\s+"authenticated_read_house_teaser"\s+'
        r"ON\s+public\.daily_snapshots",
        sql,
        re.I,
    )
    # Research teasers on theses/instruments must remain (T5 Observer).
    assert not re.search(
        r'DROP\s+POLICY\s+IF\s+EXISTS\s+"authenticated_read_house_teaser"\s+'
        r"ON\s+public\.theses",
        sql,
        re.I,
    )
    assert not re.search(
        r'DROP\s+POLICY\s+IF\s+EXISTS\s+"authenticated_read_house_teaser"\s+'
        r"ON\s+public\.instruments",
        sql,
        re.I,
    )


def test_still_drops_anon_read_on_book_tables(sql: str) -> None:
    for table in BOOK_TABLES:
        assert re.search(
            rf'DROP\s+POLICY\s+IF\s+EXISTS\s+"anon_read"\s+ON\s+public\.{table}',
            sql,
            re.I,
        ), table


def test_post_cutover_proof_expects_zero_house_book_for_non_members() -> None:
    """Harness applies 900; 109 teaser must not be encoded as post-cutover PASS."""
    proof = (REPO_ROOT / "scripts" / "rls_proof" / "02_proof.sql").read_text(encoding="utf-8")
    assert "user_a_custom', 'positions', 'house', '0'" in proof
    assert "user_c_free', 'positions', 'no_private', '0'" in proof


def test_pre_cutover_110_proof_expects_house_book_for_anon() -> None:
    """110 proof runs before 900: anon still sees house, never overlay."""
    pre = (
        REPO_ROOT / "scripts" / "rls_proof" / "02_pre_cutover_110.sql"
    ).read_text(encoding="utf-8")
    assert "positions_total" in pre
    assert "'1'" in pre
    assert "overlay_positions_hidden" in pre
    assert "overlay_docs_hidden" in pre
    assert "BEFORE 900" in pre or "before 900" in pre.lower()
    # Must not encode the post-cutover anon-positions=0 contract.
    assert "SELECT count(*)::text FROM public.positions', '0'" not in pre
