"""Tests for Slapper calibration loading (file + Supabase)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digiquant.strategies.calibrations_loader import (
    load_calibrations_file,
    merge_trade_start,
    resolve_calibrations,
)


def test_merge_trade_start() -> None:
    out = merge_trade_start({"rsi_length": 14}, "2018-01-01")
    assert out["trade_start"] == "2018-01-01"
    assert out["rsi_length"] == 14


def test_resolve_from_example_file(tmp_path: Path) -> None:
    cal_path = tmp_path / "calibrations.json"
    cal_path.write_text(json.dumps({"btc_slapper": {"rsi_length": 21}}))
    cal = resolve_calibrations(
        "btc_slapper",
        source="file",
        trade_start="2018-01-01",
        file_path=cal_path,
    )
    assert cal["rsi_length"] == 21
    assert cal["trade_start"] == "2018-01-01"


def test_load_calibrations_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_calibrations_file(tmp_path / "nope.json")
