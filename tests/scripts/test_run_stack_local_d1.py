"""DIG-2901 (supabase exit 13): run_stack_local.sh local D1 parity guards.

Schema-only until ticket 0 (DIG-2888 snapshot) exists: the stack script must
start dashboard-api via `wrangler dev --persist-to` on a LOCAL-only config,
gate seeding on the snapshot dir, and leave prod bindings and Supabase alone.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_stack_local.sh"
LOCAL_TOML = ROOT / "apps" / "dashboard-api" / "wrangler.local.toml"
PROD_TOML = ROOT / "apps" / "dashboard-api" / "wrangler.toml"
MIGRATION = ROOT / "apps" / "dashboard-api" / "d1-local" / "migrations" / "0001_schema.sql"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_stack_script_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, f"bash -n failed:\n{result.stderr}"


@pytest.mark.unit
def test_stack_script_uses_local_d1_persist_to() -> None:
    body = _read(SCRIPT)
    assert "--persist-to" in body
    assert "wrangler.local.toml" in body
    assert "wrangler deploy" not in body


@pytest.mark.unit
def test_stack_script_seed_gated_on_snapshot() -> None:
    body = _read(SCRIPT)
    assert "SUPABASE_EXIT_SNAPSHOT_DIR" in body
    assert "d1-seed.sql" in body
    assert "--local" in body
    # Schema-only notice when no snapshot is present.
    assert "schema-only" in body


@pytest.mark.unit
def test_local_config_has_no_prod_surface() -> None:
    lines = [
        line.split("#", 1)[0]
        for line in _read(LOCAL_TOML).splitlines()
    ]
    config = "\n".join(lines)
    assert "DASHBOARD_D1" in config
    assert "migrations_dir" in config
    assert "SUPABASE" not in config
    assert "[[routes]]" not in config
    assert "custom_domain" not in config


@pytest.mark.unit
def test_prod_wrangler_toml_untouched_by_local_d1() -> None:
    body = _read(PROD_TOML)
    assert "d1_databases" not in body


@pytest.mark.unit
def test_placeholder_migration_is_schema_only() -> None:
    body = _read(MIGRATION)
    assert "CREATE TABLE IF NOT EXISTS d1_local_schema_version" in body
    for keyword in ("COPY", "pg_dump", "SUPABASE", "d1-seed"):
        assert keyword not in body
