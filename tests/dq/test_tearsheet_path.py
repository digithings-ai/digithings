"""Tearsheet output path containment."""

from __future__ import annotations

import pytest

from digiquant.nautilus_runner import _resolve_tearsheet_output


@pytest.mark.unit
def test_resolve_tearsheet_relative_under_results_dir() -> None:
    out = _resolve_tearsheet_output("run.html")
    assert "backtest_results" in str(out)


@pytest.mark.unit
def test_resolve_tearsheet_rejects_escape() -> None:
    with pytest.raises(ValueError, match="tearsheet_path"):
        _resolve_tearsheet_output("/etc/passwd")
