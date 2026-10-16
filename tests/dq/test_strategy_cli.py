"""Unit tests for `digiquant strategy list|search` (#160)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from digiquant.cli import main as digiquant_main
from digiquant.cli.strategy import strategy as strategy_group

_SAMPLE = [
    {
        "name": "ema_cross",
        "aliases": ["ema"],
        "description": "EMA crossover trend",
        "default_params": {"fast": 10, "slow": 20},
    },
    {
        "name": "bollinger_mr",
        "aliases": ["bb"],
        "description": "Bollinger mean reversion",
        "default_params": {"period": 20},
    },
]


@pytest.mark.unit
def test_strategy_list_json() -> None:
    runner = CliRunner()
    with patch(
        "digiquant.service.service_list_strategies", return_value=_SAMPLE
    ) as list_fn:
        result = runner.invoke(strategy_group, ["list"])
    assert result.exit_code == 0, result.output
    list_fn.assert_called_once_with()
    assert json.loads(result.output) == _SAMPLE


@pytest.mark.unit
def test_strategy_search_filters_name_and_description() -> None:
    runner = CliRunner()
    with patch("digiquant.service.service_list_strategies", return_value=_SAMPLE):
        by_name = runner.invoke(strategy_group, ["search", "bollinger"])
        by_alias = runner.invoke(strategy_group, ["search", "ema"])
        by_desc = runner.invoke(strategy_group, ["search", "mean reversion"])
        empty = runner.invoke(strategy_group, ["search", "no-such-strategy"])
    assert by_name.exit_code == 0
    assert json.loads(by_name.output) == [_SAMPLE[1]]
    assert by_alias.exit_code == 0
    assert json.loads(by_alias.output) == [_SAMPLE[0]]
    assert by_desc.exit_code == 0
    assert json.loads(by_desc.output) == [_SAMPLE[1]]
    assert empty.exit_code == 0
    assert json.loads(empty.output) == []


@pytest.mark.unit
def test_strategy_search_rejects_blank_query() -> None:
    result = CliRunner().invoke(strategy_group, ["search", "   "])
    assert result.exit_code != 0


@pytest.mark.unit
def test_strategy_group_registered_on_main() -> None:
    result = CliRunner().invoke(digiquant_main, ["strategy", "--help"])
    assert result.exit_code == 0, result.output
    assert "list" in result.output
    assert "search" in result.output
