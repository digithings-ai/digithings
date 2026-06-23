"""Unit tests for migration 045 (PM Direction Memo doc_type — #1005).

#930 introduced a new ``documents`` artifact published with
``doc_type="PM Direction Memo"`` (``commit_io.publish_hermes_documents``), but no
migration ever added that value to the ``chk_documents_doc_type`` CHECK constraint
(latest before 045 was 043, which only permits the legacy ``"PM Allocation Memo"``).
The mismatch was masked by the date-serialization crash (#993/#994); once that was
fixed the row reached Postgres and was rejected (APIError 23514).

These tests assert the *latest* doc_type constraint permits every doc_type the
publish code actually writes — the regression guard that would have caught #1005 —
and that 045 extends rather than narrows the prior allow-list.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3] / "digiquant" / "supabase" / "migrations"
)
COMMIT_IO = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "olympus"
    / "hermes"
    / "writers"
    / "commit_io.py"
)

# Full allow-list as of migration 043 — 045 must preserve every entry (no regression),
# including the legacy ``PM Allocation Memo`` retained for historical rows.
DOC_TYPES_043 = frozenset(
    {
        "Daily Digest",
        "Daily Delta",
        "Weekly Rollup",
        "Monthly Summary",
        "Deep Dive",
        "Research Delta",
        "Research Baseline Manifest",
        "Document Delta",
        "Research Changelog",
        "Rebalance Decision",
        "Asset Recommendation",
        "Deliberation Transcript",
        "Deliberation Session Index",
        "Market Thesis Exploration",
        "Thesis Vehicle Map",
        "PM Allocation Memo",
        "Sector Report",
        "Evolution Sources",
        "Evolution Quality Log",
        "Evolution Proposals",
        "Pipeline Review",
        "Custom Research",
        "Beliefs",
    }
)

_ADD_CONSTRAINT = "ADD CONSTRAINT chk_documents_doc_type"
_MIGRATION_NUM_RE = re.compile(r"^(\d+)_")
_QUOTED_RE = re.compile(r"'([^']+)'")


def _migration_number(path: Path) -> int:
    m = _MIGRATION_NUM_RE.match(path.name)
    assert m, f"migration filename lacks numeric prefix: {path.name}"
    return int(m.group(1))


def _latest_doctype_constraint() -> tuple[Path, str]:
    """The highest-numbered migration that (re)defines ``chk_documents_doc_type``."""
    matches = [
        (p, txt)
        for p in MIGRATIONS_DIR.glob("*.sql")
        if _ADD_CONSTRAINT in (txt := p.read_text(encoding="utf-8"))
    ]
    assert matches, "no migration defines chk_documents_doc_type"
    return max(matches, key=lambda pair: _migration_number(pair[0]))


def _allowed_doc_types(constraint_sql: str) -> frozenset[str]:
    """Extract the quoted IN(...) members of the doc_type CHECK constraint."""
    add_idx = constraint_sql.index(_ADD_CONSTRAINT)
    # The IN(...) list lives between the constraint clause and its closing ');'.
    in_clause = constraint_sql[add_idx:]
    return frozenset(_QUOTED_RE.findall(in_clause))


@pytest.fixture(scope="module")
def latest() -> tuple[Path, frozenset[str]]:
    path, sql = _latest_doctype_constraint()
    return path, _allowed_doc_types(sql)


@pytest.mark.unit
class TestDocTypeConstraintPermitsPmDirectionMemo:
    def test_latest_constraint_permits_pm_direction_memo(
        self, latest: tuple[Path, frozenset[str]]
    ) -> None:
        """The new #930 doc_type must be in the latest constraint (RED until 045)."""
        path, allowed = latest
        assert "PM Direction Memo" in allowed, (
            f"'PM Direction Memo' missing from {path.name}; commit_io writes it "
            f"and Postgres rejects rows whose doc_type is not in the constraint"
        )

    def test_latest_constraint_preserves_043_doc_types(
        self, latest: tuple[Path, frozenset[str]]
    ) -> None:
        """045 extends, never narrows: every 043 value still permitted."""
        _path, allowed = latest
        missing = DOC_TYPES_043 - allowed
        assert not missing, f"latest doc_type constraint dropped: {sorted(missing)}"

    def test_commit_io_pm_direction_doc_type_is_constraint_allowed(
        self, latest: tuple[Path, frozenset[str]]
    ) -> None:
        """Every doc_type literal the publish code writes must be DB-allowed."""
        _path, allowed = latest
        src = COMMIT_IO.read_text(encoding="utf-8")
        literals = set(re.findall(r'doc_type="([^"]+)"', src))
        assert literals, "expected at least one doc_type= literal in commit_io.py"
        disallowed = literals - allowed
        assert not disallowed, (
            f"commit_io.py writes doc_type(s) not in chk_documents_doc_type: "
            f"{sorted(disallowed)}"
        )
