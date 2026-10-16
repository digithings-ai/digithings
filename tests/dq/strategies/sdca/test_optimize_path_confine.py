"""load_sdca_ohlcv confines the symbol-derived path inside data_dir (#5888)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.optimize import _first_existing, load_sdca_ohlcv

pytestmark = pytest.mark.unit


def test_traversal_symbol_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe characters"):
        load_sdca_ohlcv(symbols=["../evil"], data_path=None, data_dir=str(tmp_path))


def test_absolute_symbol_refused(tmp_path):
    with pytest.raises(ValueError, match="unsafe characters"):
        load_sdca_ohlcv(symbols=["/etc/passwd"], data_path=None, data_dir=str(tmp_path))


def test_missing_symbol_file_raises_not_found(tmp_path):
    with pytest.raises(Exception):
        load_sdca_ohlcv(symbols=["BTC-USD"], data_path=None, data_dir=str(tmp_path))


def test_first_existing_returns_directory_entry(tmp_path):
    (tmp_path / "M2SL.csv").write_text("a")
    (tmp_path / "M2.csv").write_text("b")
    hit = _first_existing(tmp_path, ("M2SL.csv", "M2.csv"))
    assert hit is not None
    assert hit == tmp_path / "M2SL.csv"


def test_first_existing_prefers_first_present_name(tmp_path):
    (tmp_path / "M2.csv").write_text("b")
    hit = _first_existing(tmp_path, ("M2SL.csv", "M2.csv"))
    assert hit is not None and hit.name == "M2.csv"


def test_first_existing_ignores_traversal_names(tmp_path):
    (tmp_path / "M2SL.csv").write_text("x")
    assert _first_existing(tmp_path, ("../M2SL.csv",)) is None
    assert _first_existing(tmp_path, ("..",)) is None
    assert _first_existing(tmp_path, ("/etc/passwd",)) is None
    assert _first_existing(tmp_path, ("sub/../../M2SL.csv",)) is None
    assert _first_existing(tmp_path, ()) is None


def test_first_existing_missing_root_and_dirs(tmp_path):
    assert _first_existing(tmp_path / "nope", ("M2SL.csv",)) is None
    (tmp_path / "M2SL.csv").mkdir()
    assert _first_existing(tmp_path, ("M2SL.csv",)) is None
