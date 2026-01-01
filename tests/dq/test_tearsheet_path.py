"""Tearsheet output path containment."""

from __future__ import annotations

from pathlib import Path

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


@pytest.mark.unit
def test_resolve_tearsheet_accepts_the_real_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link_parent = tmp_path / "cwd"
    link_parent.mkdir()
    (link_parent / "backtest_results").symlink_to(real)
    monkeypatch.chdir(link_parent)
    out = _resolve_tearsheet_output(real / "run.html")
    assert out == (real / "run.html").resolve()


@pytest.mark.unit
def test_resolve_tearsheet_rejects_a_sibling_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "backtest_results").mkdir()
    sibling = tmp_path / "backtest_results_evil"
    sibling.mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="tearsheet_path"):
        _resolve_tearsheet_output(sibling / "run.html")


@pytest.mark.unit
def test_resolve_tearsheet_rejects_a_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "backtest_results"
    base.mkdir()
    outside = tmp_path / "secret.html"
    outside.write_text("nope", encoding="utf-8")
    (base / "escape.html").symlink_to(outside)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="tearsheet_path"):
        _resolve_tearsheet_output("escape.html")
