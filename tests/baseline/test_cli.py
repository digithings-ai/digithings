"""Baseline CLI help tests — verify click entrypoints register cleanly.

Uses click.testing.CliRunner (in-process) so no PYTHONPATH gymnastics or
subprocess spawn are needed. Tests only --help, which never hits external
services.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from digiquant.cli import main as digiquant_main


@pytest.mark.baseline
def test_digiquant_cli_help() -> None:
    """Top-level digiquant CLI group registers and returns exit code 0."""
    result = CliRunner().invoke(digiquant_main, ["--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.baseline
def test_digiquant_prices_help() -> None:
    """digiquant prices subgroup registers and returns exit code 0."""
    result = CliRunner().invoke(digiquant_main, ["prices", "--help"])
    assert result.exit_code == 0, result.output


@pytest.mark.baseline
def test_digiquant_backtest_help() -> None:
    """digiquant backtest command registers and returns exit code 0."""
    result = CliRunner().invoke(digiquant_main, ["backtest", "--help"])
    assert result.exit_code == 0, result.output
    assert "--strategy" in result.output
