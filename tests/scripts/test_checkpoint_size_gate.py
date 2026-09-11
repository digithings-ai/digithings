"""Unit tests for the advisory post-archive size gate (issue #3811)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "digiquant_checkpoint_size_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("size_gate", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["size_gate"] = module
    spec.loader.exec_module(module)
    return module


def test_gate_ok_below_threshold() -> None:
    gate = _load()
    ok, report = gate.evaluate_sizes({"checkpoint_blobs": 100.0}, 488.0, 500.0)
    assert ok
    assert "488.0" in report


def test_gate_breach_above_threshold() -> None:
    gate = _load()
    ok, report = gate.evaluate_sizes({"checkpoint_blobs": 200.0}, 588.0, 500.0)
    assert not ok
    assert "EXCEEDED" in report


def test_gate_boundary_is_ok() -> None:
    gate = _load()
    ok, _ = gate.evaluate_sizes({}, 500.0, 500.0)
    assert ok


def test_main_fail_open_without_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = _load()
    monkeypatch.delenv("CORE_POSTGRES_URI", raising=False)
    assert gate.main(["--threshold-mb", "500"]) == 0
    assert gate.main(["--threshold-mb", "500", "--strict"]) == 2
