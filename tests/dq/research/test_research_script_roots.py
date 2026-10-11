"""Operator scripts must resolve the research package, not digiquant/scripts/.

``Path(__file__).parent.parent`` from ``digiquant/scripts/research`` is
``digiquant/scripts``. RUNBOOK, templates, config, and scratch data are not
there, so preflight and schema lookup used to miss every file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "research"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _load(name: str, filename: str | None = None):
    path = _SCRIPTS / (filename or f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"research_roots_{name}", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_watchlist_includes_spy_from_the_research_package() -> None:
    from lib.watchlist import WATCHLIST_PATH, parse_tickers_from_watchlist

    assert WATCHLIST_PATH.is_file()
    assert "SPY" in parse_tickers_from_watchlist()


def test_scratch_cache_lives_under_digiquant_data() -> None:
    from lib.roots import DIGIQUANT_ROOT
    from lib.scratch_paths import AGENT_CACHE_ROOT

    assert AGENT_CACHE_ROOT == DIGIQUANT_ROOT / "data" / "agent-cache"
    assert (DIGIQUANT_ROOT / "data").is_dir()


def test_macro_manifest_is_the_research_config() -> None:
    from lib.macro_ingest import MANIFEST_PATH

    assert MANIFEST_PATH.is_file()


def test_validate_artifact_finds_research_and_portfolio_schemas() -> None:
    mod = _load("validate_artifact")
    weekly = mod._schema_path_for("weekly_digest")
    rebalance = mod._schema_path_for("rebalance_decision")
    assert weekly.is_file()
    assert rebalance.is_file()
    assert weekly.parent != rebalance.parent


def test_run_db_first_preflight_paths_exist() -> None:
    mod = _load("run_db_first")
    missing = [str(path) for path in mod.PREFLIGHT_PATHS if not path.exists()]
    assert missing == []
    opened = mod._execute_at_open_argv("2026-06-19")
    assert Path(opened[1]).is_file()


def test_generate_snapshot_reads_package_config_and_schema() -> None:
    from lib.roots import DIGIQUANT_ROOT

    mod = _load("generate_snapshot", "generate-snapshot.py")
    assert mod.PORTFOLIO_JSON.is_file()
    assert mod.SCHEMA_PATH.is_file()
    assert mod.DAILY_DIR == DIGIQUANT_ROOT / "data" / "agent-cache" / "daily"


def test_materialize_snapshot_schema_exists() -> None:
    mod = _load("materialize_snapshot")
    assert mod.SCHEMA_PATH.is_file()


def test_normalize_loads_the_portfolio_rebalance_schema() -> None:
    mod = _load("normalize_supabase_documents")
    schema = mod.schema_for_kind("rebalance_decision")
    assert isinstance(schema, dict) and schema


def test_tearsheet_outputs_land_in_the_dashboard_app() -> None:
    import update_tearsheet as ut

    assert ut.OUTPUT_JSON.parent.is_dir()
    assert "scripts" not in ut.OUTPUT_JSON.parts
    assert ut.PORTFOLIO_JSON.is_file()


def test_tearsheet_root_alias_is_digiquant_root() -> None:
    """backfill-supabase.py calls load_all_markdowns(mod.ROOT) once any digest exists."""
    import update_tearsheet as ut
    from lib.roots import DIGIQUANT_ROOT

    assert ut.ROOT == DIGIQUANT_ROOT
    assert ut.load_all_markdowns(ut.ROOT) == ut.load_all_markdowns(DIGIQUANT_ROOT)


def test_backfill_export_defaults_to_digiquant_data() -> None:
    from lib.roots import DIGIQUANT_ROOT

    mod = _load("backfill_export_state")
    assert mod.DEFAULT_OUT == DIGIQUANT_ROOT / "data" / "backfill-backup"


def test_backfill_pm_loads_its_sibling_script() -> None:
    mod = _load("backfill_pm_rebalance_and_activity")
    assert mod.research_script("execute_at_open.py").is_file()
    assert mod.schema_file("rebalance-decision.schema.json").is_file()


def test_fold_points_at_sibling_scripts() -> None:
    mod = _load("fold_document_deltas")
    assert mod.research_script("materialize_snapshot.py").is_file()
    assert mod.research_script("validate_artifact.py").is_file()
    assert mod.research_script("publish_document.py").is_file()
