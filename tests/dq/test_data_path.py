"""REM-055: data_path must stay under DIGIQUANT_DATA_ROOT."""

from __future__ import annotations

from pathlib import Path

import pytest

from digiquant.paths import validate_data_paths


@pytest.mark.unit
def test_validate_data_paths_accepts_under_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    csv = root / "AAPL.csv"
    csv.write_text("date,open,high,low,close,volume\n")
    monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(root))
    validate_data_paths(data_path=csv, data_dir=None)


@pytest.mark.unit
def test_validate_data_paths_rejects_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("x")
    monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(root))
    with pytest.raises(ValueError, match="data_path"):
        validate_data_paths(data_path=outside, data_dir=None)
