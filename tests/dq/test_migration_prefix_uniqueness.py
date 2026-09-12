"""Guard the `core` migration chain: version prefixes must be unique.

Regression coverage for #3923 — the duplicate `025` prefix (thesis daily fields +
trading calendar) and the CI duplicate check that only warned.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
VERIFY_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "research" / "verify-supabase-migrations.sh"
DB_MIGRATE = REPO_ROOT / ".github" / "workflows" / "db-migrate.yml"


def _prefixes() -> list[str]:
    return [
        p.stem.split("_", 1)[0]
        for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
    ]


def test_no_duplicate_version_prefixes() -> None:
    prefixes = _prefixes()
    assert prefixes, "no migrations found"
    dups = {ver: n for ver, n in Counter(prefixes).items() if n > 1}
    assert dups == {}, f"duplicate migration version prefix(es): {dups}"


def test_025_collision_resolved() -> None:
    assert not (MIGRATIONS_DIR / "025_trading_calendar.sql").exists()
    assert (MIGRATIONS_DIR / "025_thesis_daily_fields.sql").is_file()
    renamed = MIGRATIONS_DIR / "126_trading_calendar.sql"
    assert renamed.is_file()
    assert "126_trading_calendar.sql" in renamed.read_text(encoding="utf-8").splitlines()[0]


def test_verify_guard_has_no_grandfather_exemptions() -> None:
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "GRANDFATHERED_DUPES" not in script
    assert "duplicate migration prefix" in script.lower()


def test_db_migrate_fails_on_duplicates_not_warns() -> None:
    workflow = DB_MIGRATE.read_text(encoding="utf-8")
    assert "::warning::duplicate migration" not in workflow
    assert "::error::duplicate migration version prefix" in workflow
    tail = workflow.split("::error::duplicate migration version prefix", 1)[1]
    assert "exit 1" in tail[:400], "duplicate check must exit non-zero"
