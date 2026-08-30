"""execute_at_open Kairos venue-dispatch seam (K4 review probes)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — fake Supabase client rows

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "atlas" / "execute_at_open.py"
)


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("execute_at_open_k4", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Avoid colliding with the atlas test module name if both load in one session.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_garbage_workspace_env_falls_back_to_house(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load()
    venue = mod.resolve_execution_venue_for_run("not-a-uuid")
    assert venue == "paper_internal"
    err = capsys.readouterr().err
    assert "not a valid UUID" in err or "OLYMPUS_KAIROS_WORKSPACE_ID" in err


def test_empty_workspace_env_is_house() -> None:
    mod = _load()
    assert mod.resolve_execution_venue_for_run(None) == "paper_internal"
    assert mod.resolve_execution_venue_for_run("") == "paper_internal"
    assert mod.resolve_execution_venue_for_run("   ") == "paper_internal"
