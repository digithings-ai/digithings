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


def _big_reference(out: Path) -> str:
    return (out / "acme-sdk" / "references" / "big.json.md").read_text()


def test_compile_truncates_large_file_by_default(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    # Comfortably over the 200k-char default per-file cap.
    (src / "big.json").write_text("x" * 250_000)
    out = tmp_path / "out"

    result = runner.invoke(app, ["compile", str(src), "--name", "acme-sdk", "--out", str(out)])

    assert result.exit_code == 0, result.output
    assert "truncated" in result.output  # warning surfaced on stderr
    assert _big_reference(out).count("x") <= 200_000


def test_max_file_chars_flag_lifts_truncation(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "big.json").write_text("x" * 250_000)
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "compile",
            str(src),
            "--name",
            "acme-sdk",
            "--out",
            str(out),
            "--max-file-chars",
            "300000",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "truncated" not in result.output
    assert _big_reference(out).count("x") == 250_000
