"""CLI tests. Skipped unless typer (the [service] extra) is installed."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from digivault.cli import app  # noqa: E402

pytestmark = pytest.mark.unit

runner = CliRunner()


def test_init_and_lint(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".digivault.yml").is_file()

    (tmp_path / "a.md").write_text("links [[b]]\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("leaf\n", encoding="utf-8")
    ok = runner.invoke(app, ["lint", "--root", str(tmp_path)])
    assert ok.exit_code == 0
    assert "vault OK" in ok.stdout


def test_lint_fails_on_unresolved(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("links [[missing]]\n", encoding="utf-8")
    result = runner.invoke(app, ["lint", "--root", str(tmp_path)])
    assert result.exit_code == 1


def test_new_note(tmp_path: Path) -> None:
    result = runner.invoke(app, ["new-note", "hello", "--title", "Hi", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "hello.md").is_file()


def test_missing_root_errors() -> None:
    result = runner.invoke(app, ["lint"])
    assert result.exit_code == 2
