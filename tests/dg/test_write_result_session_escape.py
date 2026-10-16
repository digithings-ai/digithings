"""write_result must not escape the current session via output_name traversal."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from digigraph.tools.analytics.data_manipulation._helpers import write_result


@pytest.fixture()
def run_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DIGI_RUN_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.unit
def test_write_result_rejects_relative_traversal(run_data: Path) -> None:
    victim = run_data / "victim" / "datasets"
    victim.mkdir(parents=True)
    victim_file = victim / "search_1.json"
    victim_file.write_text(json.dumps([{"keep": True}]), encoding="utf-8")

    out = write_result(
        pl.DataFrame({"evil": [1]}),
        "attacker",
        "../../victim/datasets/search_1",
    )

    assert out["dataset_ref"] is None
    assert "error" in out
    assert json.loads(victim_file.read_text(encoding="utf-8")) == [{"keep": True}]
    assert not (run_data / "attacker" / "datasets" / "../../victim/datasets/search_1.json").exists()


@pytest.mark.unit
def test_write_result_rejects_absolute_output_name(run_data: Path) -> None:
    victim = run_data / "victim" / "datasets"
    victim.mkdir(parents=True)
    target = victim / "pwned.json"

    out = write_result(
        pl.DataFrame({"evil": [1]}),
        "attacker",
        str(target.with_suffix("")),  # absolute path without .json; helper adds .json
    )

    assert out["dataset_ref"] is None
    assert "error" in out
    assert not target.exists()


@pytest.mark.unit
def test_write_result_writes_under_session_when_name_safe(run_data: Path) -> None:
    out = write_result(pl.DataFrame({"a": [1, 2]}), "sess-a", "merged_1")
    assert "error" not in out
    assert out["dataset_ref"]
    path = Path(out["dataset_ref"])
    assert path.exists()
    assert path.parent == (run_data / "sess-a" / "datasets").resolve()
    assert path.name == "merged_1.json"
    assert out["rows"] == 2


@pytest.mark.unit
def test_write_result_size_cap_does_not_fallback(
    run_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_a, **_k):
        raise ValueError("Dataset size 99.00 MB exceeds the configured cap of 1.0 MB")

    monkeypatch.setattr(
        "digigraph.digistore.digistore_put",
        _boom,
    )
    out = write_result(pl.DataFrame({"a": [1]}), "sess-a", "big")
    assert out["dataset_ref"] is None
    assert "exceeds the configured cap" in out["error"]
    assert not (run_data / "sess-a" / "datasets" / "big.json").exists()
