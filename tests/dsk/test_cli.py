"""CLI tests. Skipped unless typer (the `[cli]` extra) is installed."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from digiskills.cli import app  # noqa: E402

pytestmark = pytest.mark.unit

runner = CliRunner()


def test_compile_writes_package(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "README.md").write_text("# Acme\n\nUse get_widget().\n")
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "compile",
            str(src),
            "--name",
            "acme-sdk",
            "--description",
            "Acme docs",
            "--out",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out / "acme-sdk" / "SKILL.md").exists()


def test_compile_requires_name(tmp_path: Path) -> None:
    result = runner.invoke(app, ["compile", str(tmp_path)])
    assert result.exit_code != 0


def test_compile_zip_flag(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "README.md").write_text("content\n")
    out = tmp_path / "out"

    result = runner.invoke(
        app, ["compile", str(src), "--name", "acme-sdk", "--out", str(out), "--zip"]
    )

    assert result.exit_code == 0, result.output
    assert (out / "acme-sdk.zip").exists()
