"""Guard the `core` migration chain: version prefixes must be unique and ordered.

Also pins the two invariants the local-stack slice added to the same guard
(DIG-2760): `[db].major_version` is 17, and every file under
`migrations/cutover/` is declared exactly once in the script's CUTOVER_ORDER.

Regression coverage for #3923 — the duplicate `025` prefix (thesis daily fields +
trading calendar), the CI duplicate check that only warned, and the ordering bug
where renumbering the calendar creator *above* its consumer (`116`) broke a fresh
apply.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
VERIFY_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "research" / "verify-supabase-migrations.sh"
CALENDAR_CREATOR = MIGRATIONS_DIR / "111_trading_calendar.sql"
POLICY_CONSUMER = MIGRATIONS_DIR / "116_authenticated_read_public_reference.sql"


def _prefixes() -> list[str]:
    return [p.stem.split("_", 1)[0] for p in sorted(MIGRATIONS_DIR.glob("*.sql"))]


def _declared_cutover() -> list[str]:
    """Cutover files the guard's CUTOVER_ORDER manifest expects, read from the script.

    Read rather than hardcoded so adding a cutover file cannot silently make
    this fixture incomplete (the guard would then fail for a reason unrelated
    to whatever a test is asserting).
    """
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    block = text.split("CUTOVER_ORDER=(", 1)[1].split(")", 1)[0]
    return re.findall(r'"([^"]+\.sql)"', block)


def _fake_chain(
    root: Path,
    names: list[str],
    *,
    config: str | None = None,
    cutover: list[str] | None = None,
    declare_extra: list[str] | None = None,
) -> Path:
    """Build a throwaway migration tree the guard can run against, untouched repo.

    The stub is deliberately *valid* for every check the guard makes that has
    nothing to do with the argument under test: config.toml pins
    `[db].major_version`, and the cutover directory carries exactly the files
    the script's manifest declares. `config`/`cutover` override that so a test
    can drive one specific failure. `declare_extra` adds an entry to the copied
    script's CUTOVER_ORDER, which is the only way to reach the collision branch
    (an undeclared file is rejected earlier, by the "declared exactly once" check).
    """
    pkg = root / "digiquant"
    script = pkg / "scripts" / "research" / VERIFY_SCRIPT.name
    script.parent.mkdir(parents=True)
    source = VERIFY_SCRIPT.read_text(encoding="utf-8")
    for extra in declare_extra or []:
        head, _, rest = source.partition("CUTOVER_ORDER=(\n")
        assert rest, "CUTOVER_ORDER manifest not found in the guard"
        close = rest.index("\n)\n")
        source = head + 'CUTOVER_ORDER=(\n' + f'  "{extra}"\n' + rest[:close] + "\n)\n" + rest[close + 3 :]
    script.write_text(source, encoding="utf-8")
    mig = pkg / "supabase" / "migrations"
    mig.mkdir(parents=True)
    cfg = "[db]\nmajor_version = 17\n" if config is None else config
    (pkg / "supabase" / "config.toml").write_text(cfg, encoding="utf-8")
    for name in names:
        (mig / name).write_text("SELECT 1;\n", encoding="utf-8")
    files = _declared_cutover() if cutover is None else cutover
    if files:
        cut = mig / "cutover"
        cut.mkdir()
        for name in files:
            (cut / name).write_text("SELECT 1;\n", encoding="utf-8")
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


# --- DIG-2760: the invariants this slice added to the same guard -------------


def test_fixture_is_valid_so_the_new_checks_are_not_vacuous(tmp_path: Path) -> None:
    """Control: a well-formed stub passes. Without this the negatives below
    could pass for a reason that has nothing to do with what they assert."""
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"]))
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_guard_requires_pg17_pin(tmp_path: Path) -> None:
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"], config="# stub\n"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "No major_version in the [db] table" in result.stderr


def test_verify_guard_rejects_a_non_17_pin(tmp_path: Path) -> None:
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"], config="[db]\nmajor_version = 16\n"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "is 16, expected 17" in result.stderr


def test_verify_guard_ignores_major_version_in_db_pooler(tmp_path: Path) -> None:
    """`[db.pooler]` is a different table; its pin must not satisfy `[db]`."""
    config = "[db]\n# no pin here\n\n[db.pooler]\nmajor_version = 17\n"
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"], config=config))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "No major_version in the [db] table" in result.stderr


def test_verify_guard_fails_on_a_missing_cutover_dir(tmp_path: Path) -> None:
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"], cutover=[]))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Missing" in result.stderr


def test_verify_guard_fails_on_an_undeclared_cutover_file(tmp_path: Path) -> None:
    files = [*_declared_cutover(), "901_extra.sql"]
    result = _run_guard(_fake_chain(tmp_path, ["001_a.sql"], cutover=files))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "901_extra.sql appears 0x in CUTOVER_ORDER" in result.stderr


def test_verify_guard_fails_on_a_cutover_prefix_collision(tmp_path: Path) -> None:
    files = [*_declared_cutover(), "002_dup.sql"]
    result = _run_guard(
        _fake_chain(
            tmp_path,
            ["001_a.sql", "002_b.sql"],
            cutover=files,
            declare_extra=["002_dup.sql"],
        )
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Prefix 002 is used by both" in result.stderr
