"""load_sdca_ohlcv confines the symbol-derived path inside data_dir (#5888)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv

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
