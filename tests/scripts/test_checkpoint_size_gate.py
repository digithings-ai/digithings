"""Unit tests for the post-archive size-relief gate (issue #3968)."""

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


def test_fails_when_no_relief_under_ceiling() -> None:
    """The #3832 defect: 450MB (< 500 ceiling) but zero shrink must FAIL."""
    gate = _load()
    pre = {"checkpoints": 100.0, "checkpoint_blobs": 80.0}
    post = {"checkpoints": 100.0, "checkpoint_blobs": 80.0}
    ok, report = gate.evaluate_relief(pre, post, 450.0, 500.0)
    assert not ok
    assert "RELIEF GATE FAILED" in report


def test_passes_with_real_relief() -> None:
    gate = _load()
    pre = {"checkpoints": 100.0, "checkpoint_blobs": 80.0}
    post = {"checkpoints": 60.0, "checkpoint_blobs": 30.0}
    ok, report = gate.evaluate_relief(pre, post, 450.0, 500.0)
    assert ok
    assert "relief" in report.lower()


def test_fails_when_tables_grow() -> None:
    gate = _load()
    ok, report = gate.evaluate_relief({"checkpoints": 100.0}, {"checkpoints": 120.0}, 450.0, 500.0)
    assert not ok
    assert "RELIEF GATE FAILED" in report


def test_fails_below_minimum_relief() -> None:
    gate = _load()
    ok, report = gate.evaluate_relief(
        {"checkpoints": 100.0}, {"checkpoints": 99.5}, 450.0, 500.0, min_relief_mb=5.0
    )
    assert not ok
    assert "minimum" in report


def test_ceiling_is_secondary_guard() -> None:
    gate = _load()
    ok, report = gate.evaluate_relief({"checkpoints": 100.0}, {"checkpoints": 50.0}, 588.0, 500.0)
    assert not ok
    assert "CEILING EXCEEDED" in report


def test_snapshot_round_trip(tmp_path: Path) -> None:
    gate = _load()
    path = tmp_path / "pre.json"
    path.write_text(gate.snapshot_to_json({"checkpoints": 12.5}, 488.0), encoding="utf-8")
    tables, db_mb = gate.load_snapshot(path)
    assert tables == {"checkpoints": 12.5}
    assert db_mb == 488.0


def test_main_fail_open_without_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = _load()
    monkeypatch.delenv("CORE_POSTGRES_URI", raising=False)
    assert gate.main(["--snapshot-out", "/tmp/pre.json"]) == 0
    assert gate.main(["--snapshot-out", "/tmp/pre.json", "--strict"]) == 2


def test_main_requires_snapshot_mode() -> None:
    gate = _load()
    with pytest.raises(SystemExit):
        gate.main(["--threshold-mb", "500"])


def test_main_strict_db_error_is_loud(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _load()
    monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://x/y")

    def boom(_uri: str) -> tuple[dict[str, float], float]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gate, "read_sizes", boom)
    assert gate.main(["--snapshot-out", str(tmp_path / "p.json")]) == 0
    assert "connection refused" in capsys.readouterr().err
    assert gate.main(["--snapshot-out", str(tmp_path / "p.json"), "--strict"]) == 2


def test_main_compare_fails_then_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gate = _load()
    pre_path = tmp_path / "pre.json"
    pre_path.write_text(gate.snapshot_to_json({"checkpoints": 100.0}, 450.0), encoding="utf-8")
    monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://x/y")
    monkeypatch.setattr(gate, "read_sizes", lambda _uri: ({"checkpoints": 100.0}, 450.0))
    assert gate.main(["--pre-snapshot", str(pre_path)]) == 1
    monkeypatch.setattr(gate, "read_sizes", lambda _uri: ({"checkpoints": 40.0}, 450.0))
    assert gate.main(["--pre-snapshot", str(pre_path)]) == 0


def test_main_missing_pre_snapshot_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _load()
    monkeypatch.setenv("CORE_POSTGRES_URI", "postgresql://x/y")
    monkeypatch.setattr(gate, "read_sizes", lambda _uri: ({"checkpoints": 40.0}, 450.0))
    assert gate.main(["--pre-snapshot", str(tmp_path / "missing.json")]) == 2
    assert "could not read pre-snapshot" in capsys.readouterr().err
