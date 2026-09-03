"""Unit tests for scripts/build_sdca_coinbase_cache.py's macro-sibling copy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_PATH = Path(__file__).resolve().parents[4] / "digiquant" / "scripts" / "build_sdca_coinbase_cache.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_sdca_coinbase_cache", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_macro_siblings_copies_present_files(tmp_path: Path) -> None:
    module = _load_script()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "M2SL.csv").write_text("date,value\n2020-01-01,1\n")
    (source / "DTWEXBGS.csv").write_text("date,value\n2020-01-01,2\n")

    copied = module.copy_macro_siblings(source, target)

    assert sorted(copied) == ["DTWEXBGS.csv", "M2SL.csv"]
    assert (target / "M2SL.csv").read_text() == "date,value\n2020-01-01,1\n"
    assert (target / "DTWEXBGS.csv").read_text() == "date,value\n2020-01-01,2\n"


def test_copy_macro_siblings_skips_missing_source(tmp_path: Path) -> None:
    module = _load_script()
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "M2SL.csv").write_text("date,value\n2020-01-01,1\n")

    copied = module.copy_macro_siblings(source, target)

    assert copied == ["M2SL.csv"]
    assert not (target / "DTWEXBGS.csv").exists()
