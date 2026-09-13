"""Guard the `core` migration chain: version prefixes must be unique and ordered.

Regression coverage for #3923 — the duplicate `025` prefix (thesis daily fields +
trading calendar), the CI duplicate check that only warned, and the ordering bug
where renumbering the calendar creator *above* its consumer (`116`) broke a fresh
apply.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
VERIFY_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "research" / "verify-supabase-migrations.sh"
DB_MIGRATE = REPO_ROOT / ".github" / "workflows" / "db-migrate.yml"
CALENDAR_CREATOR = MIGRATIONS_DIR / "111_trading_calendar.sql"
POLICY_CONSUMER = MIGRATIONS_DIR / "116_authenticated_read_public_reference.sql"


def _prefixes() -> list[str]:
    return [p.stem.split("_", 1)[0] for p in sorted(MIGRATIONS_DIR.glob("*.sql"))]


def _fake_chain(root: Path, names: list[str]) -> Path:
    """Build a throwaway migration tree the guard can run against, untouched repo."""
    pkg = root / "digiquant"
    script = pkg / "scripts" / "research" / VERIFY_SCRIPT.name
    script.parent.mkdir(parents=True)
    script.write_text(VERIFY_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    mig = pkg / "supabase" / "migrations"
    mig.mkdir(parents=True)
    (pkg / "supabase" / "config.toml").write_text("# stub\n", encoding="utf-8")
    for name in names:
        (mig / name).write_text("SELECT 1;\n", encoding="utf-8")
    return script


def _run_guard(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script)], capture_output=True, text=True)


def test_no_duplicate_version_prefixes() -> None:
    prefixes = _prefixes()
    assert prefixes, "no migrations found"
    dups = {ver: n for ver, n in Counter(prefixes).items() if n > 1}
    assert dups == {}, f"duplicate migration version prefix(es): {dups}"


def test_025_collision_resolved() -> None:
    assert not (MIGRATIONS_DIR / "025_trading_calendar.sql").exists()
    assert (MIGRATIONS_DIR / "025_thesis_daily_fields.sql").is_file()
    assert CALENDAR_CREATOR.is_file()
    assert (
        "111_trading_calendar.sql" in CALENDAR_CREATOR.read_text(encoding="utf-8").splitlines()[0]
    )


def test_trading_calendar_precedes_its_policy_consumer() -> None:
    """The creator must sort before 116, which runs CREATE POLICY ON it (#3923)."""
    assert "public.trading_calendar" in POLICY_CONSUMER.read_text(encoding="utf-8")
    assert CALENDAR_CREATOR.name[:3] < POLICY_CONSUMER.name[:3]


def test_verify_guard_has_no_grandfather_exemptions() -> None:
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "GRANDFATHERED_DUPES" not in script
    assert "duplicate migration prefix" in script.lower()


def test_verify_guard_passes_unique_chain(tmp_path: Path) -> None:
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql", "002_b.sql"]))
    assert result.returncode == 0, result.stderr
    assert "prefixes unique" in result.stdout


def test_verify_guard_fails_on_duplicate_prefix(tmp_path: Path) -> None:
    result = _run_guard(_fake_chain(tmp_path, ["025_a.sql", "025_b.sql"]))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Duplicate migration prefix 025" in result.stderr


def test_db_migrate_fails_on_duplicates_not_warns() -> None:
    workflow = DB_MIGRATE.read_text(encoding="utf-8")
    assert "::warning::duplicate migration" not in workflow
    assert "::error::duplicate migration version prefix" in workflow
    tail = workflow.split("::error::duplicate migration version prefix", 1)[1]
    assert "exit 1" in tail[:400], "duplicate check must exit non-zero"
